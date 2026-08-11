"""Password hashing for stored application-user accounts.

Uses bcrypt (``bcrypt``), the de-facto standard password hash, via the
library's self-describing hash format (version + cost + salt + digest). We never
invent a custom scheme: ``hash_password`` produces a bcrypt hash; ``verify_password``
parses the stored hash and re-derives it in constant-time-per-cost. Plaintext is
held only for the lifetime of the setup/login request and is never logged,
persisted, or returned.

bcrypt is limited to 72-byte passwords (it raises on longer inputs); the API
policy rejects passwords over 72 bytes so the limit can never be hit
silently.

``normalize_username`` is the single normalization rule shared by setup and
login so both surfaces treat identical usernames identically.
"""

from __future__ import annotations

import bcrypt

#: bcrypt hard limit — ``hashpw`` raises on anything longer.
BCRYPT_MAX_BYTES = 72


def hash_password(plaintext: str) -> str:
    """Return a bcrypt hash for ``plaintext`` (never stored in the clear)."""
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(plaintext: str, stored_hash: str) -> bool:
    """Return whether ``plaintext`` matches a stored bcrypt hash.

    Never raises on malformed hashes or oversized inputs — anything unusable is
    treated as "does not match" so a corrupted row can never leak a prematurely
    successful login.
    """
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("utf-8"))
    except (ValueError, TypeError):
        return False


def normalize_username(raw: str) -> str:
    """Normalize a username for comparison and storage.

    Surrounding whitespace is stripped exactly once; the returned value is what
    gets stored and compared. Setup and login apply this identical transform so
    a username created at setup is found again at login no matter how it was
    typed. Case is preserved (setup stores and login compares exactly).
    """
    return raw.strip()