"""Focused tests for the first-run administrator setup flow.

Covers the product contract for replacing environment-defined browser
credentials with a stored-account setup wizard:

- fresh installations report setup required (and only then)
- the first administrator is created exactly once, race-safe, with a stored
  bcrypt hash (never plaintext) after policy validation
- confirm-mismatch / weak / malformed input is rejected
- a second setup attempt fails closed (409) and the wizard is gone forever
- successful setup opens the normal browser session, after which login,
  logout, programmatic API keys, WebSocket/SSE and chat isolation all keep
  working; roles stay correct
- passwords/hashes never appear in API responses or logs

Each "fresh" scenario runs against its own throwaway database so no test
depends on the shared run-wide database or on test ordering.
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.passwords import hash_password, verify_password
from app.db.user_store import UserStore
from app.main import create_app
from database.schema import Base
from tests.auth import admin_headers, readonly_headers, setup_admin
from tests.unit.test_auth_api import _canned_update, _FakeFeed
from tests.unit.test_browser_login import _NoProviderService

SETUP_PASSWORD = "s3cure-Admin-password-42"
READONLY_PASSWORD = "s3cure-Readonly-password-42"


@contextmanager
def _isolated_client(tmp_path) -> Iterator[TestClient]:
    """TestClient whose user store targets a fresh, empty database."""
    app = _isolated_app(tmp_path)
    with TestClient(app) as client:
        yield client


def _isolated_app(tmp_path):
    """Build an app whose user store targets a fresh, empty database."""
    engine = create_engine(
        f"sqlite:///{tmp_path}/users.db",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    store = UserStore(session_factory=session_factory)
    app = create_app()
    app.state.user_store = store
    app.state.env_bootstrap_enabled = False
    return app


def _seed_readonly(client: TestClient) -> None:
    """Insert the read-only account once the initial admin exists."""
    client.app.state.user_store.insert_user(
        username="viewer",
        password_hash=hash_password(READONLY_PASSWORD),
        role="readonly",
    )


# ── 1..2. fresh installation requires setup ────────────────────────────────


def test_fresh_installation_requires_setup(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        response = client.get("/api/v1/setup/status")
        assert response.status_code == 200
        assert response.json() == {"setup_required": True}


def test_setup_status_reports_complete_once_user_exists(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        response = client.get("/api/v1/setup/status")
        assert response.status_code == 200
        assert response.json() == {"setup_required": False}


# ── 3..4. first administrator creation & password storage ──────────────────


def test_first_administrator_is_created(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        assert body["role"] == "admin"
        assert body["token"]
        assert body["expires_at"]
        assert body["ttl_seconds"] > 0


def test_password_stored_hashed_never_plaintext(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        record = client.app.state.user_store.get_by_username("admin")
        assert record is not None
        assert record.role == "admin"
        # The stored value is a bcrypt hash, not the submitted password.
        assert record.password_hash != SETUP_PASSWORD
        assert SETUP_PASSWORD not in record.password_hash
        assert record.password_hash.startswith("$2")
        # And it verifies correctly against the real password.
        assert verify_password(SETUP_PASSWORD, record.password_hash)
        assert not verify_password("not-the-password", record.password_hash)


# ── 5..6. input validation ─────────────────────────────────────────────────


def test_confirm_password_mismatch_rejected(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        response = client.post(
            "/api/v1/setup/admin",
            json={
                "username": "admin",
                "password": SETUP_PASSWORD,
                "confirm_password": "different-password",
            },
        )
        assert response.status_code == 422


def test_weak_passwords_rejected(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        for weak in ["", "short", "x" * 73]:
            response = client.post(
                "/api/v1/setup/admin",
                json={
                    "username": "admin",
                    "password": weak,
                    "confirm_password": weak,
                },
            )
            assert response.status_code == 422, weak


def test_invalid_usernames_rejected(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        for bad in ["", "ab", "a b", "no@slug!", "x" * 65]:
            response = client.post(
                "/api/v1/setup/admin",
                json={
                    "username": bad,
                    "password": SETUP_PASSWORD,
                    "confirm_password": SETUP_PASSWORD,
                },
            )
            assert response.status_code == 422, bad


def test_missing_fields_rejected(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        response = client.post("/api/v1/setup/admin", json={})
        assert response.status_code == 422


# ── 7..8. single administrator / race safety ───────────────────────────────


def test_second_setup_attempt_rejected(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        # Same username and a different username both fail closed.
        for username in ("admin", "another"):
            response = client.post(
                "/api/v1/setup/admin",
                json={
                    "username": username,
                    "password": SETUP_PASSWORD,
                    "confirm_password": SETUP_PASSWORD,
                },
            )
            assert response.status_code == 409, username


def test_concurrent_setup_cannot_create_duplicate_admins(tmp_path) -> None:
    engine = create_engine(
        f"sqlite:///{tmp_path}/race.db",
        connect_args={"timeout": 10},
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(
        bind=engine,
        class_=Session,
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    store = UserStore(session_factory=session_factory)
    results: list[bool] = []
    barrier = threading.Barrier(2)

    def attempt(username: str) -> None:
        barrier.wait()
        results.append(
            store.insert_admin(
                username=username,
                password_hash=hash_password(SETUP_PASSWORD),
            )
        )

    threads = [
        threading.Thread(target=attempt, args=(f"admin{i}",)) for i in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # Exactly one of the racing request wins; the table holds one admin.
    assert sum(results) == 1
    assert store.count() == 1


# ── 9..10. post-setup state & session ──────────────────────────────────────


def test_successful_setup_creates_browser_session(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        headers = {"Authorization": f"Bearer {body['token']}"}
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200


# ── 11..13. login / logout after setup ─────────────────────────────────────


def test_normal_login_works_after_setup(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": SETUP_PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "admin"


def test_invalid_login_fails_after_setup(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "wrong-password"},
        )
        assert response.status_code == 401
        unknown = client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": SETUP_PASSWORD},
        )
        assert unknown.status_code == 401


def test_logout_still_works_after_setup(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        headers = {"Authorization": f"Bearer {body['token']}"}
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/v1/router/status", headers=headers).status_code == 401


# ── 14. programmatic API keys ──────────────────────────────────────────────


def test_api_key_authentication_still_works(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        assert client.get("/api/v1/router/status", headers=admin_headers()).status_code == 200
        assert client.get("/api/v1/router/status", headers=readonly_headers()).status_code == 200


# ── 15..16. WebSocket / SSE authentication ─────────────────────────────────


def test_websocket_authenticates_with_setup_session(tmp_path) -> None:
    app = _isolated_app(tmp_path)
    with TestClient(app) as client:
        client.app.state.snapshot_service = _FakeFeed(_canned_update())
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        with client.websocket_connect(
            f"/api/v1/dashboard/ws?token={body['token']}"
        ) as websocket:
            frame = json.loads(websocket.receive_text())
    assert frame["type"] == "update"


def test_sse_copilot_stream_authenticates_with_setup_session(tmp_path) -> None:
    app = _isolated_app(tmp_path)
    with TestClient(app) as client:
        client.app.state.chat_service = _NoProviderService()
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "hi"},
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


# ── 17. chat/RAG isolation ─────────────────────────────────────────────────


def test_chat_isolation_between_stored_account_sessions(tmp_path) -> None:
    app = _isolated_app(tmp_path)
    with TestClient(app) as client:
        client.app.state.chat_service = _NoProviderService()
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        # Two distinct sessions for the same stored admin account.
        token_a = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": SETUP_PASSWORD},
        ).json()["token"]
        token_b = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": SETUP_PASSWORD},
        ).json()["token"]
        client.post(
            "/api/v1/chat",
            json={"session_id": "iso", "message": "secret-b"},
            headers={"Authorization": f"Bearer {token_b}"},
        )
        history_a = client.get(
            "/api/v1/chat/history",
            params={"session_id": "iso"},
            headers={"Authorization": f"Bearer {token_a}"},
        )
        assert history_a.status_code == 200
        assert history_a.json()["messages"] == []


# ── 18. roles remain correct ───────────────────────────────────────────────


def test_roles_remain_correct_with_stored_accounts(tmp_path) -> None:
    with _isolated_client(tmp_path) as client:
        setup_admin(client, username="admin", password=SETUP_PASSWORD)
        _seed_readonly(client)
        admin_session = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": SETUP_PASSWORD},
        ).json()["token"]
        readonly_session = client.post(
            "/api/v1/auth/login",
            json={"username": "viewer", "password": READONLY_PASSWORD},
        ).json()["token"]
        # Admin reaches the write handler (422 = request got through, unknown kind).
        response = client.post(
            "/api/v1/router/management/jobs",
            json={"kind": "bogus-kind", "confirmed": True},
            headers={"Authorization": f"Bearer {admin_session}"},
        )
        assert response.status_code == 422
        # Readonly is denied the write boundary with 403.
        response = client.post(
            "/api/v1/router/management/jobs",
            json={"kind": "bogus-kind", "confirmed": True},
            headers={"Authorization": f"Bearer {readonly_session}"},
        )
        assert response.status_code == 403


# ── 19..20. no secrets in responses or logs ────────────────────────────────


def test_password_and_hash_never_in_api_responses(tmp_path, caplog) -> None:
    with _isolated_client(tmp_path) as client:
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        record = client.app.state.user_store.get_by_username("admin")
        assert record is not None
        responses = [
            json.dumps(body),
            client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": SETUP_PASSWORD},
            ).text,
            client.get("/api/v1/setup/status").text,
            client.get("/api/v1/auth/session",
                       headers={"Authorization": f"Bearer {body['token']}"}).text,
        ]
        for text in responses:
            assert SETUP_PASSWORD not in text
            assert record.password_hash not in text


def test_password_and_hash_never_in_logs(tmp_path, caplog) -> None:
    with caplog.at_level("DEBUG"), _isolated_client(tmp_path) as client:
        body = setup_admin(client, username="admin", password=SETUP_PASSWORD)
        client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": SETUP_PASSWORD},
        )
        client.get("/api/v1/auth/session",
                   headers={"Authorization": f"Bearer {body['token']}"})
    record = client.app.state.user_store.get_by_username("admin")
    assert record is not None
    assert SETUP_PASSWORD not in caplog.text
    assert record.password_hash not in caplog.text