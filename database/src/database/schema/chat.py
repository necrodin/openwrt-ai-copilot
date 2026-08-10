"""Chat conversation persistence.

Stores chat turns (user / assistant) per session so the AI chat UI can restore
history across reloads. Messages are append-only; sessions are just a
session_id grouping.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.schema.base import Base


class ChatMessageRecord(Base):
    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_owner_session_created", "owner", "session_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(128), nullable=False)
    # Stable per-principal namespace: chat state owned by different authenticated
    # principals never shares a session. NULL rows predate owner scoping and are
    # intentionally invisible to every principal (fail-closed).
    owner: Mapped[str | None] = mapped_column(String(128), nullable=True)
    role: Mapped[str] = mapped_column(String(32), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ChatMessageRecord session={self.session_id!r} role={self.role!r}>"
