"""Router credential encryption-at-rest tests.

Covers the AEAD credential vault:

1. a new router password is encrypted at rest,
2. a private key is encrypted at rest,
3. encrypted values decrypt for SSH use,
4. a wrong encryption key fails safely,
5. plaintext never appears in API responses,
6. plaintext never appears in logs,
7. a legacy plaintext database migrates safely,
8. migration is idempotent,
9. a missing encryption key fails/warns per the documented policy,
10. re-onboarding / IP change stays functional with encrypted credentials.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.core.vault import (
    PLACEHOLDER_SECRET_KEY,
    CredentialVault,
    VaultError,
    build_vault,
    ensure_credential_vault,
)
from app.db.router_store import store as router_store
from database.schema.router import RouterRecord, configure_secret_codec
from database.session import SessionLocal, init_db


def _save_payload(**overrides: object) -> dict:
    payload: dict = {
        "name": "Living Room",
        "host": "192.168.1.1",
        "port": 22,
        "username": "root",
        "auth_type": "password",
        "password": "topsecret",
    }
    payload.update(overrides)
    return payload


@pytest.fixture(autouse=True)
def _clean_and_reset() -> None:
    """Fresh router table per test, reset *before* the client's lifespan runs.

    The client fixture executes the app lifespan (which installs the credential
    codec and reads stored routers), so any record left over from a previous
    test that was written under a different key would break that lifespan. This
    autouse fixture therefore empties the table up front (idempotent ``init_db``
    guarantees the table exists) and always clears the secret codec afterwards.
    """
    init_db()
    for record in router_store.get_all():
        router_store.delete(record.id)
    yield
    configure_secret_codec(None)


# =============================================================================
# encryption at rest + decryption for SSH use
# =============================================================================


def test_new_router_password_is_encrypted_at_rest(client: TestClient) -> None:
    saved = client.post("/api/v1/router/save", json=_save_payload()).json()

    with SessionLocal() as session:
        record = session.get(RouterRecord, saved["id"])
        assert record is not None
        assert record._password is not None
        assert record._password.startswith("encv1:")
        assert record._password != "topsecret"


def test_new_private_key_is_encrypted_at_rest(client: TestClient) -> None:
    key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc123\n-----END OPENSSH PRIVATE KEY-----\n"
    saved = client.post(
        "/api/v1/router/save",
        json=_save_payload(auth_type="key", password=None, private_key=key),
    ).json()

    with SessionLocal() as session:
        record = session.get(RouterRecord, saved["id"])
        assert record is not None
        assert record._private_key is not None
        assert record._private_key.startswith("encv1:")
        assert record._private_key != key


def test_encrypted_values_decrypt_for_ssh_use(client: TestClient) -> None:
    saved = client.post("/api/v1/router/save", json=_save_payload()).json()
    with SessionLocal() as session:
        record = session.get(RouterRecord, saved["id"])
        # the property hands the decrypted credential to the SSH layer
        assert record.password == "topsecret"

    # the same record resolves through the store the management service uses
    latest = router_store.get_most_recent()
    assert latest.password == "topsecret"


def test_wrong_encryption_key_fails_safely(client: TestClient) -> None:
    configure_secret_codec(None)
    vault_a = CredentialVault(Fernet.generate_key().decode())
    configure_secret_codec(vault_a)
    with SessionLocal() as session:
        record = RouterRecord(
            name="r", host="10.0.0.1", username="root", password="secret"
        )
        session.add(record)
        session.commit()
        record_id = record.id

    configure_secret_codec(CredentialVault(Fernet.generate_key().decode()))
    with SessionLocal() as session:
        record = session.get(RouterRecord, record_id)
        with pytest.raises(VaultError):
            _ = record.password  # noqa: B018 - must raise under the wrong key


# =============================================================================
# no plaintext leakage
# =============================================================================


def test_plaintext_never_appears_in_api_response(client: TestClient) -> None:
    response = client.post("/api/v1/router/save", json=_save_payload(password="sup3rs3cret"))
    assert response.status_code == 200
    assert "sup3rs3cret" not in response.text

    listing = client.get("/api/v1/router/connections")
    assert "sup3rs3cret" not in listing.text


def test_plaintext_never_appears_in_logs(client: TestClient, caplog) -> None:
    with caplog.at_level(logging.DEBUG):
        client.post("/api/v1/router/save", json=_save_payload(password="sup3rs3cret"))
    assert "sup3rs3cret" not in caplog.text


# =============================================================================
# migration
# =============================================================================


def test_plaintext_database_migration_works(client: TestClient) -> None:
    configure_secret_codec(None)
    with SessionLocal() as session:
        record = RouterRecord(
            name="legacy",
            host="10.0.0.1",
            username="root",
            password="legacy-pass",
            private_key="legacy-key",
        )
        session.add(record)
        session.commit()
        record_id = record.id

    vault = build_vault(SimpleNamespace(auth_vault_key="", secret_key="a-strong-secret"))
    assert router_store.migrate_vault(vault) == 2

    configure_secret_codec(vault)
    with SessionLocal() as session:
        record = session.get(RouterRecord, record_id)
        assert record._password.startswith("encv1:")
        assert record._private_key.startswith("encv1:")
        assert record.password == "legacy-pass"
        assert record.private_key == "legacy-key"


def test_migration_is_idempotent(client: TestClient) -> None:
    configure_secret_codec(None)
    with SessionLocal() as session:
        record = RouterRecord(name="legacy", host="10.0.0.1", username="root", password="x")
        session.add(record)
        session.commit()

    vault = build_vault(SimpleNamespace(auth_vault_key="", secret_key="a-strong-secret"))
    assert router_store.migrate_vault(vault) == 1
    assert router_store.migrate_vault(vault) == 0
    assert router_store.migrate_vault(vault) == 0


# =============================================================================
# missing / invalid encryption key policy
# =============================================================================


def test_missing_key_without_records_warns_and_allows_demo(client: TestClient, caplog) -> None:
    settings = SimpleNamespace(auth_vault_key="", secret_key=PLACEHOLDER_SECRET_KEY)
    with caplog.at_level(logging.WARNING):
        result = ensure_credential_vault(settings, router_store)
    assert result is None
    assert "encryption key" in caplog.text


def test_missing_key_with_stored_records_fails_startup(client: TestClient) -> None:
    configure_secret_codec(None)
    with SessionLocal() as session:
        session.add(RouterRecord(name="r", host="10.0.0.1", username="root", password="x"))
        session.commit()

    settings = SimpleNamespace(auth_vault_key="", secret_key=PLACEHOLDER_SECRET_KEY)
    with pytest.raises(VaultError, match="AUTH_VAULT_KEY"):
        ensure_credential_vault(settings, router_store)


def test_store_refuses_credentials_without_key(client: TestClient) -> None:
    configure_secret_codec(None)
    with pytest.raises(VaultError, match="AUTH_VAULT_KEY"):
        router_store.save(name="r", host="10.0.0.1", username="root", password="x")
    assert router_store.get_all() == []


def test_invalid_auth_vault_key_raises() -> None:
    settings = SimpleNamespace(auth_vault_key="definitely-not-a-fernet-key", secret_key="")
    with pytest.raises(VaultError, match="AUTH_VAULT_KEY"):
        build_vault(settings)


def test_auth_vault_key_takes_precedence() -> None:
    key = Fernet.generate_key().decode()
    vault = build_vault(
        SimpleNamespace(auth_vault_key=key, secret_key=PLACEHOLDER_SECRET_KEY)
    )
    assert vault is not None
    token = vault.encrypt("plain")
    assert token.startswith("encv1:")
    assert vault.decrypt(token) == "plain"


# =============================================================================
# re-onboarding / IP change
# =============================================================================


def test_reonboarding_ip_change_keeps_credentials_decryptable(client: TestClient) -> None:
    first = client.post("/api/v1/router/save", json=_save_payload(host="192.168.1.1")).json()
    client.post(
        "/api/v1/router/save",
        json=_save_payload(name="Router", router_id=first["id"], host="192.168.1.42"),
    ).json()

    with SessionLocal() as session:
        record = session.get(RouterRecord, first["id"])
        assert record.host == "192.168.1.42"
        assert record._password.startswith("encv1:")
        assert record.password == "topsecret"
