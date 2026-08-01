"""SQLAlchemy engine and session factory."""

from __future__ import annotations

from sqlalchemy import create_engine
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


def init_db() -> None:
    """Create tables from the ORM metadata. Idempotent (IF NOT EXISTS)."""
    from database.schema import Base  # noqa: F401  (import registers models)

    Base.metadata.create_all(bind=engine)
