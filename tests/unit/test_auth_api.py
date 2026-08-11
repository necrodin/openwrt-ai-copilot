"""Focused authentication & authorization tests (Security Fix #1).

Covers the required boundary checks: unauthenticated rejection, read-only
allowance, management/action authorization, WebSocket/SSE authentication,
copilot (chat) authentication, and that no credentials are ever returned by,
or leaked through, the API.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.chat_service import NoChatProviderError
from app.services.demo_source import build_simulated_snapshot
from tests.auth import (
    TEST_ADMIN_KEY,
    TEST_READONLY_KEY,
    admin_headers,
    browser_login,
    readonly_headers,
    unknown_headers,
)

PASSWORD = "super-secret-ssh-password"
PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nabcd\n-----END OPENSSH PRIVATE KEY-----\n"


def _app_client(*, headers: dict[str, str] | None = None) -> TestClient:
    app = create_app()
    return TestClient(app, headers=headers) if headers else TestClient(app)


class _FakeFeed:
    """Stand-in snapshot service that immediately returns one canned update."""

    source = "simulated"

    def __init__(self, update: DashboardUpdate) -> None:
        self._update = update

    def latest(self) -> DashboardUpdate:
        return self._update

    def subscribe(self) -> asyncio.Queue[DashboardUpdate]:
        return asyncio.Queue()

    def unsubscribe(self, queue: asyncio.Queue[DashboardUpdate]) -> None:
        pass

    async def stop(self) -> None:
        pass


def _canned_update(*, sequence: int = 1) -> DashboardUpdate:
    return DashboardUpdate(
        type="update",
        sequence=sequence,
        sent_at=datetime.now(UTC),
        source="simulated",
        device_id="demo-router",
        connected=True,
        snapshot=build_simulated_snapshot(),
    )


@contextmanager
def _ws_client(update: DashboardUpdate | None = None) -> Iterator[TestClient]:
    """TestClient (no default headers) with a canned snapshot feed."""
    app = create_app()
    with TestClient(app) as client:
        app.state.snapshot_service = _FakeFeed(update or _canned_update())
        yield client


def _login(client: TestClient) -> str:
    """Mint a browser session token via the username/password login endpoint."""
    return browser_login(client)


@contextmanager
def _chat_client() -> Iterator[TestClient]:
    """TestClient (no default headers) whose chat service has no provider."""
    app = create_app()
    with TestClient(app) as client:
        client.app.state.chat_service = _NoProviderService()
        yield client


class _NoProviderService:
    """Chat service stand-in that reports no provider (deterministic 503)."""

    def provider_for(self, preference=None) -> None:
        raise NoChatProviderError("No chat provider configured")


# ── unauthenticated API requests are rejected ────────────────────────────────


@pytest.mark.parametrize(
    "method, path, payload",
    [
        ("get", "/api/v1/router/status", None),
        ("get", "/api/v1/dashboard/latest", None),
        ("get", "/api/v1/router/info", None),
        ("get", "/api/v1/providers", None),
        ("get", "/api/v1/chat/history", None),
        ("post", "/api/v1/chat", {"message": "hi"}),
        ("post", "/api/v1/router/management/jobs", {"kind": "action", "action": "reboot"}),
        ("post", "/api/v1/router/test-connection", {"host": "127.0.0.1", "password": "x"}),
        ("post", "/api/v1/router/save", {"name": "x", "host": "127.0.0.1", "password": "x"}),
    ],
)
def test_unauthenticated_request_rejected(method: str, path: str, payload: dict | None) -> None:
    with _app_client() as unauth_client:
        response = (
            getattr(unauth_client, method)(path, json=payload)
            if payload
            else getattr(unauth_client, method)(path)
        )
    assert response.status_code == 401
    assert "password" not in response.text and "Bearer" not in response.text


def test_unknown_token_rejected(client: TestClient) -> None:
    response = client.get("/api/v1/router/status", headers=unknown_headers())
    assert response.status_code == 401


# ── authenticated read-only access is allowed ────────────────────────────────


def test_readonly_key_can_read_router_status(client: TestClient) -> None:
    response = client.get("/api/v1/router/status", headers=readonly_headers())
    assert response.status_code == 200
    body = response.json()
    assert "connected" in body and "snapshot" in body and "diagnosis" in body


def test_readonly_key_can_read_providers(client: TestClient) -> None:
    response = client.get("/api/v1/providers", headers=readonly_headers())
    assert response.status_code == 200


def test_readonly_key_can_read_dashboard(client: TestClient) -> None:
    response = client.get("/api/v1/dashboard/latest", headers=readonly_headers())
    assert response.status_code == 200


# ── management/action authorization ──────────────────────────────────────────


def test_unauthenticated_management_action_rejected(client: TestClient) -> None:
    with _app_client() as unauth_client:
        response = unauth_client.post(
            "/api/v1/router/management/jobs",
            json={"kind": "action", "action": "reboot", "confirmed": True},
        )
    # auth runs before any handler logic — even an invalid kind must be 401
    assert response.status_code == 401


def test_unauthorized_management_action_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/management/jobs",
        json={"kind": "bogus-kind", "confirmed": True},
        headers=readonly_headers(),
    )
    assert response.status_code == 403


def test_authorized_management_action_reaches_handler(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/management/jobs",
        json={"kind": "bogus-kind", "confirmed": True},
        headers=admin_headers(),
    )
    # admin passed auth+authorization and reached the handler, which rejects the kind
    assert response.status_code == 422
    assert "Unsupported job kind" in response.json()["detail"]


def test_readonly_key_cannot_save_router(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/save",
        json={
            "name": "x",
            "host": "127.0.0.1",
            "port": 22,
            "username": "root",
            "password": PASSWORD,
        },
        headers=readonly_headers(),
    )
    assert response.status_code == 403


def test_admin_key_can_save_router(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/save",
        json={
            "name": "x",
            "host": "127.0.0.1",
            "port": 22,
            "username": "root",
            "password": PASSWORD,
        },
        headers=admin_headers(),
    )
    assert response.status_code == 200


# ── SSE / WebSocket ──────────────────────────────────────────────────────────


def test_unauthenticated_websocket_rejected() -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        _ws_client() as client,
        client.websocket_connect("/api/v1/dashboard/ws"),
    ):
        pass


def test_websocket_without_read_scope_rejected() -> None:
    with (
        pytest.raises(WebSocketDisconnect),
        _ws_client() as client,
        client.websocket_connect("/api/v1/dashboard/ws", headers=unknown_headers()),
    ):
        pass


def test_authenticated_websocket_allowed_via_session_query() -> None:
    # Browsers cannot set headers on the WebSocket upgrade, so they pass a
    # short-lived session token (never a static master key) in the query.
    with (
        _ws_client() as client,
        client.websocket_connect(
            f"/api/v1/dashboard/ws?token={_login(client)}"
        ) as websocket,
    ):
        frame = json.loads(websocket.receive_text())
    assert frame["type"] == "update"
    assert frame["snapshot"]["meta"]["device_id"] == "demo-router"


def test_authenticated_websocket_allowed_via_bearer_header() -> None:
    with (
        _ws_client() as client,
        client.websocket_connect("/api/v1/dashboard/ws", headers=readonly_headers()) as websocket,
    ):
        frame = json.loads(websocket.receive_text())
    assert frame["type"] == "update"


# ── AI / Copilot ─────────────────────────────────────────────────────────────


def test_unauthenticated_copilot_rejected() -> None:
    with _chat_client() as client:
        response = client.post("/api/v1/chat/stream", json={"message": "hi"})
    assert response.status_code == 401


def test_unauthorized_copilot_scenario_does_not_leak() -> None:
    # A readonly key that is valid must never receive credentials back in errors.
    with _chat_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={"message": "show wifi", "password": PASSWORD},
            headers=readonly_headers(),
        )
    # reaches handler (no provider configured) → 503; password text must not be echoed
    assert response.status_code == 503
    assert PASSWORD not in response.text


def test_authenticated_copilot_request_allowed_past_auth() -> None:
    with _chat_client() as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "auth-test", "message": "hi"},
            headers=admin_headers(),
        )
    # no provider configured → handler 503 (auth passed, request was not rejected)
    assert response.status_code == 503


def test_authenticated_copilot_history_readable_by_readonly() -> None:
    with _chat_client() as client:
        response = client.get(
            "/api/v1/chat/history",
            params={"session_id": "auth-test"},
            headers=readonly_headers(),
        )
    assert response.status_code == 200
    assert "messages" in response.json()


# ── credentials are never returned to the frontend ───────────────────────────


def test_saved_router_credentials_never_returned(client: TestClient) -> None:
    client.post(
        "/api/v1/router/save",
        json={
            "name": "secret-router",
            "host": "127.0.0.1",
            "port": 22,
            "username": "root",
            "auth_type": "password",
            "password": PASSWORD,
        },
        headers=admin_headers(),
    )
    client.post(
        "/api/v1/router/save",
        json={
            "name": "key-router",
            "host": "192.168.1.2",
            "port": 22,
            "username": "root",
            "auth_type": "key",
            "private_key": PRIVATE_KEY,
        },
        headers=admin_headers(),
    )
    connections = client.get("/api/v1/router/connections", headers=admin_headers())
    assert connections.status_code == 200
    body = connections.json()
    assert PASSWORD not in connections.text
    assert "BEGIN OPENSSH PRIVATE KEY" not in connections.text
    for router in body["routers"]:
        assert "password" not in router
        assert "private_key" not in router

    for path in [
        "/api/v1/router/status",
        "/api/v1/router/info",
        "/api/v1/router/context",
        "/api/v1/dashboard/latest",
    ]:
        response = client.get(path, headers=admin_headers())
        assert response.status_code == 200
        assert PASSWORD not in response.text
        assert "BEGIN OPENSSH PRIVATE KEY" not in response.text


def test_auth_failure_response_contains_no_secrets(client: TestClient) -> None:
    response = client.get(
        "/api/v1/router/status",
        headers={"Authorization": f"Bearer {PASSWORD}"},
    )
    assert response.status_code == 401
    assert PASSWORD not in response.text
    assert "SPRING-STAGING" not in response.text


def test_health_and_ready_remain_public(client: TestClient) -> None:
    assert client.get("/api/v1/health").status_code == 200
    assert client.get("/api/v1/ready").status_code == 200


def test_api_key_value_itself_never_returned(client: TestClient) -> None:
    response = client.get("/api/v1/router/status", headers=admin_headers())
    assert TEST_ADMIN_KEY not in response.text
    assert TEST_READONLY_KEY not in response.text
