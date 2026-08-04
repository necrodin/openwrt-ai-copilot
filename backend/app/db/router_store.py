"""Router connection persistence (SQLite via the shared database package)."""

from __future__ import annotations

from sqlalchemy import select

from database.schema.router import RouterRecord
from database.session import SessionLocal


class RouterStore:
    """Store for the routers configured through the onboarding wizard."""

    def save(
        self,
        *,
        name: str,
        host: str,
        port: int = 22,
        username: str = "root",
        auth_type: str = "password",
        password: str | None = None,
        private_key: str | None = None,
        device_id: str | None = None,
    ) -> RouterRecord:
        """Insert a new router connection record."""
        with SessionLocal() as session:
            record = RouterRecord(
                name=name,
                host=host,
                port=port,
                username=username,
                auth_type=auth_type,
                password=password,
                private_key=private_key,
                device_id=device_id,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return record

    def get_all(self) -> list[RouterRecord]:
        """Return every saved router, most recent first."""
        with SessionLocal() as session:
            stmt = select(RouterRecord).order_by(RouterRecord.created_at.asc())
            return list(session.scalars(stmt).all())

    def get_most_recent(self) -> RouterRecord | None:
        """Return the most recently saved router, if any."""
        with SessionLocal() as session:
            stmt = (
                select(RouterRecord)
                .order_by(RouterRecord.created_at.desc(), RouterRecord.id.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()

    def delete(self, router_id: int) -> None:
        """Delete a router connection record."""
        with SessionLocal() as session:
            session.query(RouterRecord).filter(RouterRecord.id == router_id).delete()
            session.commit()

    def to_public_dict(self, record: RouterRecord) -> dict:
        """Return a JSON-safe view of a record (never includes secrets)."""
        return {
            "id": record.id,
            "name": record.name,
            "host": record.host,
            "port": record.port,
            "username": record.username,
            "auth_type": record.auth_type,
            "device_id": record.device_id,
            "created_at": record.created_at.isoformat() if record.created_at else None,
        }


store = RouterStore()
