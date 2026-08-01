"""Security helpers.

Sprint 1 foundation: placeholder for the security primitives used by later
sprints (API key derivation, encryption envelope, signing for audit events).
Nothing here is wired into the API yet.
"""

from hashlib import sha256

from app.core.config import settings


def derive_secret_key() -> bytes:
    """Domain-separated key material derived from the configured secret."""
    return sha256(f"openwrt-ai:v1:{settings.secret_key}".encode()).digest()
