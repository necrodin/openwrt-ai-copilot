"""Persisted application user accounts (first-run administrator setup).

Browser users authenticate against these records. Only ``password_hash`` is
stored (bcrypt); the plaintext password is validated once by the setup/login
endpoints and never persisted, logged, or returned by the API.

Enforced invariants:

- ``username`` is unique.
- At most one row may carry the ``admin`` role, enforced by a SQLite partial
  unique index. This makes the first-run setup endpoint race-safe: no matter
  how many simultaneous ``POST /setup/admin`` requests arrive, an admin row
  can be created only when the users table is empty and only once.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from database.schema.base import Base


class AppUserRecord(Base):
    __tablename__ = "app_users"
    __table_args__ = (
        # SQLite-specific backstop for the (already atomic) setup insert: a raw
        # or racing INSERT can never add a second administrator row.
        Index(
            "uq_app_users_single_admin",
            "role",
            unique=True,
            sqlite_where=text("role = 'admin'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="admin")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AppUserRecord id={self.id} role={self.role!r} username={self.username!r}>"