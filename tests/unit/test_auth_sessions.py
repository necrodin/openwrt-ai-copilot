"""Focused security tests for the browser-session auth layer.

Proves the behavior required of the secure browser auth flow:
- login issues a session scoped exactly to the minting key (admin vs read-only)
- login rejects bad keys and never leaks either master key
- login is the only new public surface; every protected route still 401s
- sessions can be introspected and expire
- logout revokes a session server-side (a revoked token is immediately rejected)
- the dashboard WebSocket accepts a live session token and rejects it after
  logout (token-style upgrades with session, never a master key)
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.auth import ADMIN_SCOPES
from app.main import create_app
from tests.auth import TEST_ADMIN_KEY, TEST_READONLY_KEY
from tests.unit.test_auth_api import _canned_update, _FakeFeed


@contextmanager
def _live_client() -> Iterator[TestClient]:
    """TestClient with full lifecycle and an isolated SessionStore per app."""
    with TestClient(create_app()) as client:
        yield client


@contextmanager
def _session_ws_client() -> Iterator[TestClient]:
    """TestClient whose snapshot feed always yields one canned update."""
    app = create_app()
    with TestClient(app) as client:
        app.state.snapshot_service = _FakeFeed(_canned_update())
        yield client


def _login(client: TestClient, api_key: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"api_key": api_key})
    assert response.status_code == 200
    return response.json()


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin_token(client: TestClient) -> str:
    return _login(client, TEST_ADMIN_KEY)["token"]


# ── login ──────────────────────────────────────────────────────────────────


def test_login_with_admin_key_mints_admin_session() -> None:
    with _live_client() as client:
        body = _login(client, TEST_ADMIN_KEY)
        assert body["role"] == "admin"
        assert body["token"]
        assert body["expires_at"]
        assert body["ttl_seconds"] > 0
        headers = _bearer(body["token"])
        # The minted session reads protected router data…
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200
        # …and reaches write handlers as admin (rejected only for the bad kind).
        response = client.post(
            "/api/v1/router/management/jobs",
            json={"kind": "bogus-kind", "confirmed": True},
            headers=headers,
        )
        assert response.status_code == 422


def test_login_with_readonly_key_mints_readonly_session() -> None:
    with _live_client() as client:
        body = _login(client, TEST_READONLY_KEY)
        assert body["role"] == "readonly"
        headers = _bearer(body["token"])
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200
        response = client.post(
            "/api/v1/router/management/jobs",
            json={"kind": "bogus-kind", "confirmed": True},
            headers=headers,
        )
        assert response.status_code == 403


def test_login_with_unknown_key_rejected() -> None:
    with _live_client() as client:
        response = client.post("/api/v1/auth/login", json={"api_key": "wrong-key"})
        assert response.status_code == 401


def test_login_response_never_contains_master_keys() -> None:
    with _live_client() as client:
        text = json.dumps(_login(client, TEST_ADMIN_KEY))
        assert TEST_ADMIN_KEY not in text
        assert TEST_READONLY_KEY not in text


def test_login_does_not_open_other_routes() -> None:
    with _live_client() as client:
        # The only unauthenticated access granted is the ability to attempt a
        # login; every protected route still rejects unauthenticated callers.
        assert client.get("/api/v1/router/status").status_code == 401


# ── session introspection & expiry ─────────────────────────────────────────


def test_session_endpoint_reports_role_and_expiry() -> None:
    with _live_client() as client:
        body = client.get("/api/v1/auth/session", headers=_bearer(_admin_token(client))).json()
        assert body["role"] == "admin"
        assert body["token_type"] == "session"
        assert body["expires_at"]


def test_unauthenticated_session_endpoint_rejected() -> None:
    with _live_client() as client:
        assert client.get("/api/v1/auth/session").status_code == 401


def test_expired_session_rejected(client: TestClient) -> None:
    store = client.app.state.auth_sessions
    past = datetime.now(UTC) - timedelta(seconds=1)
    token, _record = store.create(role="admin", scopes=ADMIN_SCOPES, expires_at=past)
    assert client.get("/api/v1/router/status", headers=_bearer(token)).status_code == 401
    assert store.revoke(token) is False  # already expired/removed


# ── logout revocation ──────────────────────────────────────────────────────


def test_logout_revokes_the_session() -> None:
    with _live_client() as client:
        headers = _bearer(_admin_token(client))
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/v1/router/status", headers=headers).status_code == 401


def test_logout_requires_authentication() -> None:
    with _live_client() as client:
        assert client.post("/api/v1/auth/logout").status_code == 401


# ── WebSocket ──────────────────────────────────────────────────────────────


def test_websocket_accepts_session_token_then_rejects_after_logout() -> None:
    with _session_ws_client() as client:
        token = _admin_token(client)
        headers = _bearer(token)
        with client.websocket_connect(f"/api/v1/dashboard/ws?token={token}") as websocket:
            frame = json.loads(websocket.receive_text())
        assert frame["type"] == "update"
        # Same live client, same token — logout must revoke it server-side.
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        with (
            pytest.raises(WebSocketDisconnect),
            client.websocket_connect(f"/api/v1/dashboard/ws?token={token}"),
        ):
            pass
