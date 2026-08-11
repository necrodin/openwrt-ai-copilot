"""Persisted router connection records.

Stores the routers added through the onboarding wizard so the app can reconnect
to them across restarts. Only connection metadata is kept; the live snapshot
feed (SnapshotService) is driven from these records at startup and after a
save.

Router credentials (``password`` / ``private_key``) are never persisted in
plaintext when a secret codec is configured: the ``password`` and
``private_key`` attributes encrypt on assignment and decrypt on read through an
injected codec (see :func:`configure_secret_codec`), so the raw column holds
only ciphertext. The codec is provided by the backend (AES/Fernet via
``cryptography``); this package only defines the seam. Decrypted values are
exposed to callers at the point where an SSH connection is built and are never
returned by the API.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from database.schema.base import Base


class SecretCodec(Protocol):
    """Encrypt/decrypt transform applied to router credentials at rest."""

    prefix: str

    def encrypt(self, plaintext: str) -> str: ...

    def decrypt(self, stored: str) -> str: ...


#: Active credential codec, injected by the backend at startup.
_codec: SecretCodec | None = None


def configure_secret_codec(codec: SecretCodec | None) -> None:
    """Set the credential codec used for new writes and reads (None = legacy)."""
    global _codec
    _codec = codec


def secret_codec() -> SecretCodec | None:
    """Return the currently configured credential codec, if any."""
    return _codec


def _encode_secret(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    codec = _codec
    return codec.encrypt(plaintext) if codec is not None else plaintext


def _decode_secret(stored: str | None) -> str | None:
    if stored is None:
        return None
    codec = _codec
    if codec is not None and stored.startswith(codec.prefix):
        return codec.decrypt(stored)
    return stored


class RouterRecord(Base):
    __tablename__ = "routers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    host: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False, default=22)
    username: Mapped[str] = mapped_column(String(128), nullable=False, default="root")
    auth_type: Mapped[str] = mapped_column(String(32), nullable=False, default="password")
    _password: Mapped[str | None] = mapped_column("password", Text, nullable=True)
    _private_key: Mapped[str | None] = mapped_column("private_key", Text, nullable=True)
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

    @property
    def password(self) -> str | None:
        """Decrypted router password (encrypted at rest when a codec is set)."""
        return _decode_secret(self._password)

    @password.setter
    def password(self, value: str | None) -> None:
        self._password = _encode_secret(value)

    @property
    def private_key(self) -> str | None:
        """Decrypted router private key (encrypted at rest when a codec is set)."""
        return _decode_secret(self._private_key)

    @private_key.setter
    def private_key(self, value: str | None) -> None:
        self._private_key = _encode_secret(value)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RouterRecord id={self.id} name={self.name!r} host={self.host!r}>"
