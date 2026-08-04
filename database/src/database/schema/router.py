"""Persisted router connection records.

Stores the routers added through the onboarding wizard so the app can reconnect
to them across restarts. Only connection metadata is kept; the live snapshot
feed (SnapshotService) is driven from these records at startup and after a
save.

Note: passwords and private keys are stored as provided (self-hosted tool); the
value is never returned by the API, only used to open SSH connections.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.schema.base import Base


class RouterRecord(Base):
    __tablename__ = "routers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    username: Mapped[str] = mapped_column(String(128), nullable=False, default="root")
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="password")
    password: Mapped[str | None] = mapped_column(Text, nullable=True)
    private_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    device_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
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
        return f"<RouterRecord id={self.id} name={self.name!r} host={self.host!r}>"
