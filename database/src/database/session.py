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


def init_db() -> None:
    """Create tables from the ORM metadata. Idempotent (IF NOT EXISTS)."""
    from database.schema import Base  # noqa: F401  (import registers models)

    Base.metadata.create_all(bind=engine)
    _migrate_chat_owner_column()
