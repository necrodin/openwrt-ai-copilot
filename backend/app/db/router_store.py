"""Router connection persistence (SQLite via the shared database package).

Credentials (``password`` / ``private_key``) are encrypted at rest through the
``RouterRecord`` secret codec (see ``app.core.vault``): the store only ever
writes ciphertext and refuses to persist credentials while no encryption key is
configured. Decrypted values are handed to SSH callers via the record's
``password``/``private_key`` properties.
"""

from __future__ import annotations

from collections.abc import Callable

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.vault import ENC_PREFIX, VaultError
from database.schema.router import RouterRecord, secret_codec
from database.session import SessionLocal

SessionFactory = Callable[[], Session]


class RouterStore:
    """Store for the routers configured through the onboarding wizard."""

    def __init__(self, session_factory: SessionFactory = SessionLocal) -> None:
        """Bind the store to ``session_factory`` (defaults to the shared engine)."""
        self._session_factory = session_factory

    def _apply(
        self,
        record: RouterRecord,
        *,
        name: str,
        host: str,
        port: int,
        username: str,
        auth_type: str,
        password: str | None,
        private_key: str | None,
        device_id: str | None,
    ) -> RouterRecord:
        record.name = name
        record.host = host
        record.port = port
        record.username = username
        record.auth_type = auth_type
        record.password = password
        record.private_key = private_key
        record.device_id = device_id
        return record

    def _assert_encryption_available(
        self, *, password: str | None, private_key: str | None
    ) -> None:
        if (password or private_key) and secret_codec() is None:
            raise VaultError(
                "The credential vault is not available. Restart the application "
                "to re-initialize the router credential vault, then save again."
            )

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
        self._assert_encryption_available(password=password, private_key=private_key)
        with self._session_factory() as session:
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

    def upsert(
        self,
        *,
        router_id: int | None,
        name: str,
        host: str,
        port: int = 22,
        username: str = "root",
        auth_type: str = "password",
        password: str | None = None,
        private_key: str | None = None,
        device_id: str | None = None,
    ) -> tuple[RouterRecord, bool]:
        """Update ``router_id`` if given, else the most recent router if any.

        Returns ``(record, created)`` where ``created`` is ``True`` when a new
        row was inserted and ``False`` when an existing record was updated.
        Re-sending the wizard for an existing router therefore never produces a
        duplicate connection row.
        """
        self._assert_encryption_available(password=password, private_key=private_key)
        if router_id is not None:
            with self._session_factory() as session:
                record = session.get(RouterRecord, router_id)
                if record is None:
                    raise KeyError(f"router {router_id} does not exist")
                self._apply(
                    record,
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
                return record, False
        existing = self.get_most_recent()
        if existing is not None:
            return self.upsert(
                router_id=existing.id,
                name=name,
                host=host,
                port=port,
                username=username,
                auth_type=auth_type,
                password=password,
                private_key=private_key,
                device_id=device_id,
            )
        return (
            self.save(
                name=name,
                host=host,
                port=port,
                username=username,
                auth_type=auth_type,
                password=password,
                private_key=private_key,
                device_id=device_id,
            ),
            True,
        )

    def has_credentials(self) -> bool:
        """Return whether any stored router holds a password or private key."""
        with self._session_factory() as session:
            stmt = select(RouterRecord).where(
                or_(
                    RouterRecord._password.is_not(None),
                    RouterRecord._private_key.is_not(None),
                )
            )
            return session.scalars(stmt).first() is not None

    def has_encrypted_credentials(self) -> bool:
        """Return whether any stored credential is ciphertext (already encrypted).

        Used to distinguish an encrypted database (whose key is unrecoverable)
        from a legacy plaintext database (which can be safely migrated).
        """
        with self._session_factory() as session:
            stmt = select(RouterRecord).where(
                or_(
                    RouterRecord._password.like(f"{ENC_PREFIX}%"),
                    RouterRecord._private_key.like(f"{ENC_PREFIX}%"),
                )
            )
            return session.scalars(stmt).first() is not None

    def migrate_vault(self, codec) -> int:
        """Encrypt any legacy plaintext credentials in place. Idempotent.

        Only values lacking the codec's format prefix are rewritten, so running
        this repeatedly is a no-op after the first successful migration. Returns
        the number of credential fields encrypted.
        """
        migrated = 0
        with self._session_factory() as session:
            records = list(session.scalars(select(RouterRecord)).all())
            for record in records:
                for column in ("_password", "_private_key"):
                    raw = getattr(record, column)
                    if raw is not None and not raw.startswith(codec.prefix):
                        setattr(record, column, codec.encrypt(raw))
                        migrated += 1
            if migrated:
                session.commit()
        return migrated

    def get_all(self) -> list[RouterRecord]:
        """Return every saved router, most recent first."""
        with self._session_factory() as session:
            stmt = select(RouterRecord).order_by(RouterRecord.created_at.asc())
            return list(session.scalars(stmt).all())

    def get_most_recent(self) -> RouterRecord | None:
        """Return the most recently saved router, if any."""
        with self._session_factory() as session:
            stmt = (
                select(RouterRecord)
                .order_by(RouterRecord.created_at.desc(), RouterRecord.id.desc())
                .limit(1)
            )
            return session.scalars(stmt).first()

    def delete(self, router_id: int) -> None:
        """Delete a router connection record."""
        with self._session_factory() as session:
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
