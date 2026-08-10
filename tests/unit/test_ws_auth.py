"""Focused regression tests for WebSocket / SSE stream authentication.

Locks in the streaming auth stream (Security Fix #2 stream):

- the dashboard socket is closed (4401) before acceptance for missing,
  invalid, expired, or revoked credentials
- credentials are never accepted from the ``?token=`` query parameter unless
  they are short-lived browser session tokens — a permanent static operator
  key in the URL is rejected, so a leaked URL can never mint an immortal data
  channel
- non-browser clients may still authenticate with a static key in the
  ``Authorization`` header, and session tokens still upgrade over the query
  parameter exactly as the browser login flow expects
- cross-origin upgrades are gated on the configured CORS allow-list
- the role boundary is unchanged: a readonly session may stream the dashboard
  (reads) but cannot reach write handlers
- the SSE copilot stream rejects unauthenticated and invalid tokens with 401
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.core.auth import ADMIN_SCOPES
from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.demo_source import build_simulated_snapshot
from tests.auth import (
    TEST_ADMIN_KEY,
    TEST_READONLY_KEY,
    admin_headers,
    readonly_headers,
)

ALLOWED_ORIGIN = "http://localhost:3000"
EVIL_ORIGIN = "http://evil.example"
WS_PATH = "/api/v1/dashboard/ws"


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
def _ws_client() -> Iterator[TestClient]:
    """TestClient (no default auth headers) with a canned snapshot feed."""
    app = create_app()
    with TestClient(app) as client:
        app.state.snapshot_service = _FakeFeed(_canned_update())
        yield client


def _login(client: TestClient, api_key: str) -> str:
    response = client.post("/api/v1/auth/login", json={"api_key": api_key})
    assert response.status_code == 200
    return response.json()["token"]


def _assert_rejected(client: TestClient, path: str, code: int = 4401) -> None:
    with pytest.raises(WebSocketDisconnect) as exc_info, client.websocket_connect(path):
        pass
    assert exc_info.value.code == code


def _assert_streams(client: TestClient, path: str) -> None:
    with client.websocket_connect(path) as websocket:
        frame = json.loads(websocket.receive_text())
    assert frame["type"] == "update"


# ── unauthenticated / invalid / expired / revoked ──────────────────────────


def test_ws_without_credentials_rejected() -> None:
    with _ws_client() as client:
        _assert_rejected(client, WS_PATH)


def test_ws_invalid_token_in_query_rejected() -> None:
    with _ws_client() as client:
        _assert_rejected(client, f"{WS_PATH}?token=not-a-real-token")


def test_ws_static_admin_key_in_query_rejected() -> None:
    with _ws_client() as client:
        _assert_rejected(client, f"{WS_PATH}?token={TEST_ADMIN_KEY}")


def test_ws_static_readonly_key_in_query_rejected() -> None:
    with _ws_client() as client:
        _assert_rejected(client, f"{WS_PATH}?token={TEST_READONLY_KEY}")


def test_ws_expired_session_in_query_rejected() -> None:
    with _ws_client() as client:
        past = datetime.now(UTC) - timedelta(seconds=1)
        token, _record = client.app.state.auth_sessions.create(
            role="admin",
            scopes=ADMIN_SCOPES,
            expires_at=past,
        )
        _assert_rejected(client, f"{WS_PATH}?token={token}")


def test_ws_reconnect_after_logout_rejected() -> None:
    with _ws_client() as client:
        token = _login(client, TEST_ADMIN_KEY)
        _assert_streams(client, f"{WS_PATH}?token={token}")
        # Logout revokes the token server-side; replaying it must not reconnect.
        assert (
            client.post(
                "/api/v1/auth/logout",
                headers={"Authorization": f"Bearer {token}"},
            ).status_code
            == 200
        )
        _assert_rejected(client, f"{WS_PATH}?token={token}")


# ── accepted paths (non-browser header + browser session query) ────────────


def test_ws_session_token_in_query_accepted() -> None:
    with _ws_client() as client:
        _assert_streams(client, f"{WS_PATH}?token={_login(client, TEST_ADMIN_KEY)}")


def test_ws_readonly_session_token_in_query_accepted() -> None:
    with _ws_client() as client:
        _assert_streams(client, f"{WS_PATH}?token={_login(client, TEST_READONLY_KEY)}")


def test_ws_static_key_in_header_accepted() -> None:
    with _ws_client() as client:
        with client.websocket_connect(WS_PATH, headers=admin_headers()) as websocket:
            frame = json.loads(websocket.receive_text())
        assert frame["type"] == "update"


def test_ws_readonly_header_cannot_reach_write_handlers() -> None:
    with _ws_client() as client:
        # A readonly session streams the dashboard (reads)…
        _assert_streams(
            client,
            f"{WS_PATH}?token={_login(client, TEST_READONLY_KEY)}",
        )
        # …but the management boundary still rejects its write attempt.
        assert (
            client.post(
                "/api/v1/router/management/jobs",
                json={"kind": "bogus-kind", "confirmed": True},
                headers=readonly_headers(),
            ).status_code
            == 403
        )


# ── origin gating ──────────────────────────────────────────────────────────


def test_ws_disallowed_origin_rejected_with_valid_session() -> None:
    with _ws_client() as client:
        token = _login(client, TEST_ADMIN_KEY)
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                f"{WS_PATH}?token={token}",
                headers={"Origin": EVIL_ORIGIN},
            ),
        ):
            pass
        assert exc_info.value.code == 4401


def test_ws_allowed_origin_accepted() -> None:
    with _ws_client() as client:
        token = _login(client, TEST_ADMIN_KEY)
        with client.websocket_connect(
            f"{WS_PATH}?token={token}",
            headers={"Origin": ALLOWED_ORIGIN},
        ) as websocket:
            frame = json.loads(websocket.receive_text())
        assert frame["type"] == "update"


def test_ws_missing_origin_accepted_for_header_client() -> None:
    with _ws_client() as client:
        with client.websocket_connect(WS_PATH, headers=admin_headers()) as websocket:
            frame = json.loads(websocket.receive_text())
        assert frame["type"] == "update"


# ── SSE copilot stream ─────────────────────────────────────────────────────


def test_sse_chat_stream_requires_authentication() -> None:
    with _ws_client() as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "status?", "confirmed": True},
        )
        assert response.status_code == 401


def test_sse_chat_stream_rejects_invalid_token() -> None:
    with _ws_client() as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "status?", "confirmed": True},
            headers={"Authorization": "Bearer not-a-real-token"},
        )
        assert response.status_code == 401


def test_sse_chat_stream_session_token_authorized_boundary() -> None:
    with _ws_client() as client:
        token = _login(client, TEST_READONLY_KEY)
        response = client.post(
            "/api/v1/chat/stream",
            json={"message": "status?", "confirmed": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        # Readonly is permitted to chat; the no-provider service emits an
        # in-band error frame rather than an auth failure.
        assert response.status_code == 200
        assert "text/event-stream" in response.headers.get("content-type", "")


def test_ws_invalid_header_does_not_fall_back_to_query() -> None:
    with _ws_client() as client:
        token = _login(client, TEST_ADMIN_KEY)
        # A presented-but-invalid header credential rejects the upgrade even
        # when a valid session token sits in the query — no silent downgrade
        # from one credential channel to another.
        with (
            pytest.raises(WebSocketDisconnect) as exc_info,
            client.websocket_connect(
                f"{WS_PATH}?token={token}",
                headers={"Authorization": "Bearer not-a-real-token"},
            ),
        ):
            pass
        assert exc_info.value.code == 4401
