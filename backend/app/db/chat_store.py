"""Chat history persistence (SQLite via the shared database package)."""

from __future__ import annotations

from sqlalchemy import func, select

from database.schema.chat import ChatMessageRecord
from database.session import SessionLocal


class ChatStore:
    """Append-only store of chat turns, grouped by session id."""

    def add_message(
        self,
        *,
        session_id: str,
        role: str,
        content: str,
        provider: str | None = None,
        model: str | None = None,
    ) -> ChatMessageRecord:
        with SessionLocal() as session:
            record = ChatMessageRecord(
                session_id=session_id,
                role=role,
                content=content,
                provider=provider,
                model=model,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_messages(self, session_id: str, *, limit: int = 50) -> list[ChatMessageRecord]:
        with SessionLocal() as session:
            stmt = (
                select(ChatMessageRecord)
                .where(ChatMessageRecord.session_id == session_id)
                .order_by(ChatMessageRecord.created_at.asc(), ChatMessageRecord.id.asc())
                .limit(limit)
            )
            return list(session.scalars(stmt).all())

    def list_sessions(self, *, limit: int = 50) -> list[dict]:
        with SessionLocal() as session:
            stmt = (
                select(
                    ChatMessageRecord.session_id,
                    func.max(ChatMessageRecord.created_at).label("updated_at"),
                    func.count(ChatMessageRecord.id).label("message_count"),
                )
                .group_by(ChatMessageRecord.session_id)
                .order_by(func.max(ChatMessageRecord.created_at).desc())
                .limit(limit)
            )
            return [
                {
                    "session_id": row.session_id,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None,
                    "message_count": row.message_count,
                }
                for row in session.execute(stmt).all()
            ]


store = ChatStore()
