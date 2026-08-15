"""Encrypted store for provider API-key credentials.

The application never persists a provider API key in plaintext. Keys are held
in a small JSON file (``provider_credentials.json`` next to the provider
configuration) where every value is Fernet ciphertext produced by the shared
:class:`app.core.vault.CredentialVault` (AES-128-CBC + HMAC-SHA256). The
encryption key is stable across restarts: ``AUTH_VAULT_KEY`` when configured,
otherwise the persisted ``vault.key`` (or a ``SECRET_KEY`` derivation / freshly
generated key), exactly like router credentials.

The config file (``providers.yaml``) therefore carries provider metadata only —
never a key, never an env-var reference unless an operator chooses the legacy
path. ``GET /providers`` only ever reports a boolean ``has_credential``.

The store is process-global (configured once at application startup) so the
provider factory's credential resolver can reach it when a provider is built.
Tests reconfigure it per app with a throwaway path.
"""

from __future__ import annotations

import contextlib
import json
import os
from pathlib import Path
from typing import Any

from app.core.vault import CredentialVault
from providers.config import ProviderConfig

CREDENTIALS_FILENAME = "provider_credentials.json"


class ProviderCredentialStore:
    """Encrypt/decrypt provider API keys to a JSON file of ciphertext."""

    def __init__(self, vault: CredentialVault, path: str | Path) -> None:
        self._vault = vault
        self._path = Path(path)

    @property
    def path(self) -> Path:
        return self._path

    def _load(self) -> dict[str, str]:
        if not self._path.is_file():
            return {}
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _save(self, data: dict[str, str]) -> None:
        """Atomically persist the ciphertext file, owner-only (``0600``)."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        temp = self._path.with_suffix(".json.tmp")
        temp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        os.replace(temp, self._path)
        with contextlib.suppress(OSError):  # pragma: no cover - exotic filesystems
            os.chmod(self._path, 0o600)

    def set(self, provider_type: str, api_key: str) -> None:
        """Encrypt and persist a provider's API key."""
        data = self._load()
        data[provider_type] = self._vault.encrypt(api_key)
        self._save(data)

    def get(self, provider_type: str) -> str | None:
        """Return the decrypted key for a provider type, or ``None``."""
        token = self._load().get(provider_type)
        if not token:
            return None
        return self._vault.decrypt(token)

    def has(self, provider_type: str) -> bool:
        return bool(self._load().get(provider_type))

    def remove(self, provider_type: str) -> bool:
        """Delete a provider's stored credential; ``False`` when none existed."""
        data = self._load()
        if provider_type not in data:
            return False
        del data[provider_type]
        self._save(data)
        return True


#: Active store for the running application; installed by ``configure_store``.
_store: ProviderCredentialStore | None = None


def configure_store(store: ProviderCredentialStore | None) -> None:
    """Install the store used for provider credential resolution.

    Also registers the secure-store resolver with the provider factory so a
    provider built from a saved configuration authenticates with the stored
    key (resolved server-side, never persisted or returned).
    """
    global _store
    _store = store
    from providers.base import configure_api_key_resolver

    configure_api_key_resolver(stored_api_key)


def current_store() -> ProviderCredentialStore | None:
    return _store


def store_path(settings) -> Path:
    """Location of the encrypted credential file (next to providers.yaml)."""
    return Path(settings.provider_config_file).parent / CREDENTIALS_FILENAME


def build_store(settings, vault: CredentialVault) -> ProviderCredentialStore:
    return ProviderCredentialStore(vault, store_path(settings))


def stored_api_key(config: ProviderConfig) -> str | None:
    """Credential resolver for the provider factory (secure store first)."""
    if _store is None:
        return None
    return _store.get(config.type)


def has_stored_credential(provider_type: str) -> bool:
    return _store is not None and _store.has(provider_type)


def credentials_payload() -> dict[str, Any]:
    """Snapshot of stored credential states (booleans only, never keys)."""
    if _store is None:
        return {}
    return {provider_type: _store.has(provider_type) for provider_type in _store._load()}


__all__ = [
    "CREDENTIALS_FILENAME",
    "ProviderCredentialStore",
    "build_store",
    "configure_store",
    "credentials_payload",
    "current_store",
    "has_stored_credential",
    "store_path",
    "stored_api_key",
]