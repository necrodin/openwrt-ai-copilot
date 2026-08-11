"""Focused tests for the browser username/password login flow.

Replaces the previous API-key browser login: the login page now accepts a
username + password (configured server-side via AUTH_ADMIN_* / AUTH_READONLY_*)
and the backend mints the existing short-lived, revocable browser session.
Covers:

1. valid admin username/password login
2. invalid username/password
3. missing username
4. missing password
5. a session is created after successful login
6. an authenticated request works after login
7. logout revokes the session
8. an expired session is rejected
9. API-key authentication for programmatic clients still works
10. API keys never appear in frontend responses
11. the dashboard WebSocket authenticates with the browser session
12. the SSE copilot stream authenticates with the browser session
13. chat/RAG context isolation remains intact per principal
14. a page refresh keeps a valid session (session introspection + reuse)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.auth import ADMIN_SCOPES
from app.main import create_app
from app.services.chat_service import ChatService
from providers.factory import ProviderManager
from providers.openai import OpenAIProvider
from tests.auth import (
    TEST_ADMIN_KEY,
    TEST_ADMIN_PASSWORD,
    TEST_ADMIN_USERNAME,
    TEST_READONLY_KEY,
    TEST_READONLY_PASSWORD,
    TEST_READONLY_USERNAME,
    admin_headers,
    browser_login,
    readonly_headers,
)
from tests.unit.providers_helpers import make_provider
from tests.unit.test_auth_api import _canned_update, _FakeFeed


@contextmanager
def _live_client() -> TestClient:
    with TestClient(create_app()) as client:
        yield client


@contextmanager
def _ws_client() -> TestClient:
    """TestClient whose snapshot feed always yields one canned update."""
    app = create_app()
    with TestClient(app) as client:
        app.state.snapshot_service = _FakeFeed(_canned_update())
        yield client


def _bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 1..2. valid / invalid credentials ──────────────────────────────────────


def test_valid_admin_login_returns_session() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["role"] == "admin"
        assert body["token"]
        assert body["expires_at"]
        assert body["ttl_seconds"] > 0


def test_valid_readonly_login_returns_session() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_READONLY_USERNAME, "password": TEST_READONLY_PASSWORD},
        )
        assert response.status_code == 200
        assert response.json()["role"] == "readonly"


def test_invalid_password_rejected() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": "wrong-password"},
        )
        assert response.status_code == 401
        assert TEST_ADMIN_PASSWORD not in response.text


def test_invalid_username_rejected() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "nobody", "password": "whatever"},
        )
        assert response.status_code == 401


def test_failed_login_does_not_reveal_which_field_was_wrong() -> None:
    with _live_client() as client:
        for body in [
            {"username": "nobody", "password": TEST_ADMIN_PASSWORD},
            {"username": TEST_ADMIN_USERNAME, "password": "wrong"},
        ]:
            response = client.post("/api/v1/auth/login", json=body)
            assert response.status_code == 401
            assert response.json()["detail"] == "Invalid username or password."


# ── 3..4. missing username / password ──────────────────────────────────────


def test_missing_username_rejected() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": "", "password": TEST_ADMIN_PASSWORD},
        )
        assert response.status_code == 422


def test_missing_password_rejected() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/auth/login",
            json={"username": TEST_ADMIN_USERNAME, "password": ""},
        )
        assert response.status_code == 422


# ── 5..8. session lifecycle ────────────────────────────────────────────────


def test_session_created_after_login() -> None:
    with _live_client() as client:
        token = browser_login(client)
        record = client.app.state.auth_sessions.resolve(token)
        assert record is not None
        assert record.role == "admin"
        assert record.expires_at > datetime.now(UTC)


def test_authenticated_request_after_login() -> None:
    with _live_client() as client:
        headers = _bearer(browser_login(client))
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200


def test_logout_revokes_session() -> None:
    with _live_client() as client:
        headers = _bearer(browser_login(client))
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 200
        assert client.get("/api/v1/router/status", headers=headers).status_code == 401


def test_expired_session_rejected_after_login() -> None:
    app = create_app()
    with TestClient(app) as client:
        token, _record = client.app.state.auth_sessions.create(
            role="admin",
            scopes=ADMIN_SCOPES,
            expires_at=datetime.now(UTC) - timedelta(seconds=1),
        )
        assert client.get("/api/v1/router/status", headers=_bearer(token)).status_code == 401


# ── 9..10. API-key flow stays intact for programmatic clients ──────────────


def test_admin_api_key_still_authenticates() -> None:
    with _live_client() as client:
        assert client.get("/api/v1/router/status", headers=admin_headers()).status_code == 200


def test_readonly_api_key_still_authenticates() -> None:
    with _live_client() as client:
        assert client.get("/api/v1/router/status", headers=readonly_headers()).status_code == 200


def test_api_key_still_grant_write_management() -> None:
    with _live_client() as client:
        response = client.post(
            "/api/v1/router/management/jobs",
            json={"kind": "bogus-kind", "confirmed": True},
            headers=admin_headers(),
        )
        assert response.status_code == 422  # reached the handler


def test_api_keys_never_appear_in_frontend_responses() -> None:
    with _live_client() as client:
        login_text = json.dumps(
            client.post(
                "/api/v1/auth/login",
                json={"username": TEST_ADMIN_USERNAME, "password": TEST_ADMIN_PASSWORD},
            ).json()
        )
        session_text = client.get("/api/v1/auth/session", headers=admin_headers()).text
        assert TEST_ADMIN_KEY not in login_text
        assert TEST_READONLY_KEY not in session_text
        assert TEST_ADMIN_PASSWORD not in login_text


# ── 11. WebSocket with browser session ─────────────────────────────────────


def test_websocket_uses_browser_session() -> None:
    with _ws_client() as client:
        token = browser_login(client)
        with client.websocket_connect(f"/api/v1/dashboard/ws?token={token}") as websocket:
            frame = json.loads(websocket.receive_text())
        assert frame["type"] == "update"


def test_websocket_static_key_in_query_rejected() -> None:
    with (
        _ws_client() as client, pytest.raises(WebSocketDisconnect),
        client.websocket_connect(f"/api/v1/dashboard/ws?token={TEST_ADMIN_KEY}"),
    ):
        pass


# ── 12. SSE copilot stream with browser session ────────────────────────────


def test_sse_copilot_stream_rejects_unauthenticated() -> None:
    with _live_client() as client:
        assert client.post("/api/v1/chat/stream", json={"message": "hi"}).status_code == 401


def test_sse_copilot_stream_reaches_handler_with_session() -> None:
    app = create_app()
    with TestClient(app) as client:
        client.app.state.chat_service = _NoProviderService()
        headers = _bearer(browser_login(client))
        response = client.post("/api/v1/chat/stream", json={"message": "hi"}, headers=headers)
    # Auth passed (a 401 would be returned before the handler runs). The no-
    # provider stand-in surfaces as an SSE error event inside a 200 response.
    assert response.status_code == 200
    assert response.text.count("error") >= 1


class _NoProviderService:
    """Chat service stand-in that reports no provider (deterministic 503)."""

    def provider_for(self, preference=None):
        from app.services.chat_service import NoChatProviderError

        raise NoChatProviderError("No chat provider configured")


# ── 13. chat/RAG context isolation ─────────────────────────────────────────


def _manager(seen: dict) -> ProviderManager:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["messages"] = json.loads(request.content).get("messages", [])
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    provider = make_provider(OpenAIProvider, handler, name="primary", model="gpt-4o-mini")
    return ProviderManager({"primary": provider}, default_provider="primary")


@contextmanager
def _chat_client(seen: dict) -> TestClient:
    app = create_app()
    with TestClient(app, headers={}) as client:
        client.app.state.chat_service = ChatService(_manager(seen), lambda: None)
        yield client


def test_chat_isolation_between_two_browser_sessions() -> None:
    seen: dict = {}
    with _chat_client(seen) as client:
        headers_a = _bearer(browser_login(client))
        headers_b = _bearer(browser_login(client))
        client.post(
            "/api/v1/chat",
            json={"session_id": "iso", "message": "secret-a"},
            headers=headers_a,
        )
        history_b = client.get(
            "/api/v1/chat/history",
            params={"session_id": "iso"},
            headers=headers_b,
        )
        assert history_b.status_code == 200
        assert history_b.json()["messages"] == []


# ── 14. page refresh keeps the session valid ───────────────────────────────


def test_session_survives_revalidation_like_a_page_refresh() -> None:
    """A restored token (the refresh path) stays valid across use.

    The frontend refresh flow re-runs GET /auth/session with the stored token
    and keeps it when accepted; here the same token remains accepted across
    repeated calls the way a refreshed page reuses it.
    """
    with _live_client() as client:
        token = browser_login(client)
        headers = _bearer(token)
        assert client.get("/api/v1/auth/session", headers=headers).status_code == 200
        assert client.get("/api/v1/router/status", headers=headers).status_code == 200
        assert client.get("/api/v1/auth/session", headers=headers).status_code == 200