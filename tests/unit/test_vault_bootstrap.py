"""First-run credential vault bootstrap tests.

The vault must work without any operator-supplied key on a self-hosted first
run: a cryptographically random Fernet key is generated, persisted owner-only
into the application data directory, and reused across restarts so existing
ciphertext keeps decrypting. Explicitly configured keys keep overriding, and an
encrypted database with no recoverable key fails with an actionable message.

Covers:

1. first startup generates a vault key,
2. the key persists across restarts,
3. existing encrypted credentials decrypt after restart,
4. an explicit AUTH_VAULT_KEY overrides the generated key,
5. key file permissions are restrictive (owner-only),
6. the generated key is never logged or returned by the API,
7. a missing key with an encrypted database fails clearly.
"""

from __future__ import annotations

import logging
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.vault import (
    PLACEHOLDER_SECRET_KEY,
    VaultError,
    ensure_credential_vault,
    vault_key_path,
)
from app.db.router_store import RouterStore
from database.schema import Base
from database.schema.router import configure_secret_codec


def _make_store(tmp_path: Path) -> RouterStore:
    """A RouterStore over an isolated throwaway SQLite database."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/routers.db",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    return RouterStore(session_factory=session_factory)


def _make_settings(
    tmp_path: Path,
    *,
    auth_vault_key: str = "",
    secret_key: str = PLACEHOLDER_SECRET_KEY,
) -> SimpleNamespace:
    return SimpleNamespace(
        auth_vault_key=auth_vault_key,
        secret_key=secret_key,
        database_url=f"sqlite:///{tmp_path}/routers.db",
    )


@pytest.fixture(autouse=True)
def _reset_secret_codec() -> None:
    """Never leak a configured codec/key across tests."""
    configure_secret_codec(None)
    yield
    configure_secret_codec(None)


# ── 1. first startup generates a vault key ────────────────────────────────


def test_first_startup_generates_vault_key(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = _make_store(tmp_path)

    vault = ensure_credential_vault(settings, store)

    assert vault is not None
    key_file = vault_key_path(settings)
    assert key_file.is_file()
    persisted = key_file.read_text(encoding="utf-8").strip()
    assert Fernet(persisted)  # a valid Fernet key, not an error
    # The generated key round-trips.
    token = vault.encrypt("secret")
    assert vault.decrypt(token) == "secret"


# ── 2. the key persists across restarts ───────────────────────────────────


def test_key_persists_across_restart(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = _make_store(tmp_path)
    configure_secret_codec(None)

    first_boot = ensure_credential_vault(settings, store)
    token = first_boot.encrypt("secret")

    configure_secret_codec(None)
    second_boot = ensure_credential_vault(settings, store)

    # Same key in effect: a token from the first boot decrypts after "restart".
    assert second_boot.decrypt(token) == "secret"
    persisted = vault_key_path(settings).read_text(encoding="utf-8").strip()
    assert Fernet(persisted)


# ── 3. existing encrypted credentials decrypt after restart ───────────────


def test_existing_encrypted_credentials_decrypt_after_restart(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = _make_store(tmp_path)
    configure_secret_codec(None)

    ensure_credential_vault(settings, store)
    record = store.save(
        name="Living Room", host="192.168.1.1", username="root", password="topsecret"
    )
    assert record._password.startswith("encv1:")
    assert record._password != "topsecret"

    configure_secret_codec(None)
    ensure_credential_vault(settings, store)
    latest = store.get_most_recent()
    assert latest is not None
    assert latest.password == "topsecret"
    assert latest._password.startswith("encv1:")


# ── 4. explicit AUTH_VAULT_KEY overrides the generated key ────────────────


def test_explicit_vault_key_overrides_generated_key(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = _make_store(tmp_path)
    configure_secret_codec(None)

    generated_vault = ensure_credential_vault(settings, store)
    key_file = vault_key_path(settings)
    generated_key = key_file.read_text(encoding="utf-8").strip()

    explicit_key = Fernet.generate_key().decode("ascii")
    assert explicit_key != generated_key
    explicit_settings = _make_settings(tmp_path, auth_vault_key=explicit_key)
    configure_secret_codec(None)

    explicit_vault = ensure_credential_vault(explicit_settings, store)

    # The explicit key is in effect (generated key cannot read its tokens).
    token = explicit_vault.encrypt("secret")
    assert explicit_vault.decrypt(token) == "secret"
    with pytest.raises(VaultError):
        generated_vault.decrypt(token)
    # The persisted key file was left untouched by the explicit override.
    assert key_file.read_text(encoding="utf-8").strip() == generated_key
    assert explicit_key not in key_file.read_text(encoding="utf-8")


# ── 5. key file permissions are restrictive ───────────────────────────────


def test_key_file_permissions_are_owner_only(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = _make_store(tmp_path)

    ensure_credential_vault(settings, store)

    mode = stat.S_IMODE(vault_key_path(settings).stat().st_mode)
    assert mode == 0o600


# ── 6. generated key is never logged or returned ──────────────────────────


def test_generated_key_never_logged_or_returned(
    tmp_path: Path, caplog, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.main as main_module

    isolated_store = _make_store(tmp_path)
    monkeypatch.setattr(main_module, "router_store", isolated_store)
    # Force first-run generation instead of the SECRET_KEY-derived fallback.
    monkeypatch.setattr(main_module.settings, "secret_key", PLACEHOLDER_SECRET_KEY)
    monkeypatch.setattr(
        main_module.settings,
        "database_url",
        f"sqlite:///{tmp_path}/routers.db",
    )

    with caplog.at_level(logging.DEBUG), TestClient(main_module.create_app()) as client:
        key_file = vault_key_path(main_module.settings)
        generated_key = key_file.read_text(encoding="utf-8").strip()
        assert generated_key
        health = client.get("/api/v1/health")
        status = client.get("/api/v1/setup/status")

    assert generated_key not in caplog.text
    assert generated_key not in health.text
    assert generated_key not in status.text


# ── 7. missing key with an encrypted database fails clearly ───────────────


def test_encrypted_db_without_key_fails_clearly(tmp_path: Path) -> None:
    settings = _make_settings(tmp_path)
    store = _make_store(tmp_path)
    configure_secret_codec(None)

    ensure_credential_vault(settings, store)
    store.save(name="r", host="10.0.0.1", username="root", password="topsecret")
    vault_key_path(settings).unlink()  # the key is lost

    configure_secret_codec(None)
    with pytest.raises(VaultError) as excinfo:
        ensure_credential_vault(_make_settings(tmp_path), store)

    message = str(excinfo.value)
    assert "AUTH_VAULT_KEY" in message
    assert "vault key file" in message
    assert "restart" in message
