"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from database.config import database_url, engine_kwargs

engine = create_engine(database_url(), **engine_kwargs())

SessionLocal = sessionmaker(
    bind=engine,
    class_=Session,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
)


def _migrate_chat_owner_column() -> None:
    """Add the ``owner`` column to pre-existing ``chat_messages`` tables.

    ``create_all`` never alters existing tables; SQLite cannot add a column with
    ``CREATE TABLE IF NOT EXISTS``. This guarded ``ALTER TABLE`` backfills the
    owner-namespacing column once for databases created before owner scoping.
    Idempotent: the inspector check skips the statement when the column exists.
    """
    inspector = inspect(engine)
    if "chat_messages" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("chat_messages")}
    if "owner" in columns:
        return
    with engine.begin() as connection:
        connection.execute(
            text("ALTER TABLE chat_messages ADD COLUMN owner VARCHAR(128)")
        )


def _migrate_app_users_single_admin_index() -> None:
    """Guarantee the "at most one admin" partial index on a pre-existing table.

    ``create_all`` adds the index when the table is first created, but never
    alters existing tables. This guarded ``CREATE UNIQUE INDEX IF NOT EXISTS``
    is the idempotent backfill for a race where the users table already exists
    without it (e.g. a table created before the index was declared). It is a
    no-op on fresh databases, where ``create_all`` already created the index.
    """
    inspector = inspect(engine)
    if "app_users" not in inspector.get_table_names():
        return
    with engine.begin() as connection:
        connection.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_app_users_single_admin "
                "ON app_users (role) WHERE role = 'admin'"
            )
        )


def init_db() -> None:
    """Create tables from the ORM metadata. Idempotent (IF NOT EXISTS)."""
    from database.schema import Base  # noqa: F401  (import registers models)

    Base.metadata.create_all(bind=engine)
    _migrate_chat_owner_column()
    _migrate_app_users_single_admin_index()
