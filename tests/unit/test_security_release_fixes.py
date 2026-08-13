"""Release-readiness security regression tests (final audit fixes).

Covers:

- M1: management job read isolation (owner may read own; readonly never reads
  another principal's job; admin may inspect; unauthenticated stays 401).
- M3: raw exceptions are never returned to chat/SSE/onboarding clients; the
  full exception is logged server-side and a stable message is returned.
- L1/L5: sensitive authenticated reads are served with ``Cache-Control:
  no-store`` while the SSE stream keeps its ``no-cache`` directive.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.chat_service import ChatService
from app.services.demo_source import build_simulated_snapshot
from providers.base import BaseProvider
from providers.config import ProviderConfig
from providers.factory import ProviderManager
from tests.auth import admin_headers, readonly_headers

_SENTINEL = "provider-internal-secret-token-xyz"


class _ExplodingProvider(BaseProvider):
    """A chat-capable provider whose calls raise a distinctive internal error."""

    provider_type = "ollama"

    async def chat(self, request):
        raise RuntimeError(_SENTINEL)

    def stream(self, request):
        async def generator():
            raise RuntimeError(_SENTINEL)
            yield None  # pragma: no cover - unreachable

        return generator()


def _exploding_manager() -> ProviderManager:
    config = ProviderConfig(type="ollama", name="explode", model="m")
    return ProviderManager(
        {"explode": _ExplodingProvider(config)},
        default_provider="explode",
    )


@contextmanager
def _chat_app(manager: ProviderManager | None = None):
    """TestClient whose chat service is replaced after lifespan starts (the
    default lifespan binds the production provider manager to app.state)."""
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        service = ChatService(
            manager if manager is not None else _exploding_manager(),
            lambda: build_simulated_snapshot(),
        )
        app.state.chat_service = service
        yield client


# --------------------------------------------------------------------------- #
# M1 — management job read isolation                                          #
# --------------------------------------------------------------------------- #


def test_admin_owner_can_read_own_job() -> None:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        created = client.post(
            "/api/v1/router/management/jobs", json={"kind": "backup"}
        )
        assert created.status_code == 200, created.text
        job_id = created.json()["id"]
        read = client.get(f"/api/v1/router/management/jobs/{job_id}")
        assert read.status_code == 200
        assert read.json()["id"] == job_id


def test_readonly_cannot_read_another_principals_job() -> None:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as admin:
        created = admin.post(
            "/api/v1/router/management/jobs", json={"kind": "backup"}
        )
        job_id = created.json()["id"]
        denied = admin.get(
            f"/api/v1/router/management/jobs/{job_id}", headers=readonly_headers()
        )
        assert denied.status_code == 404  # existence is never revealed


def test_any_admin_can_inspect_jobs() -> None:
    """A second admin principal may inspect a job created by another admin."""
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        created = client.post(
            "/api/v1/router/management/jobs", json={"kind": "backup"}
        )
        job_id = created.json()["id"]
        other_admin = client.post(
            "/api/v1/auth/login",
            json={"username": "admin", "password": "test-admin-password"},
        )
        assert other_admin.status_code == 200
        token = other_admin.json()["token"]
        read = client.get(
            f"/api/v1/router/management/jobs/{job_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert read.status_code == 200
        assert read.json()["id"] == job_id


def test_job_read_unauthenticated_is_401() -> None:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as admin:
        created = admin.post(
            "/api/v1/router/management/jobs", json={"kind": "backup"}
        )
        job_id = created.json()["id"]
    with TestClient(app) as bare:
        assert (
            bare.get(f"/api/v1/router/management/jobs/{job_id}").status_code == 401
        )


def test_job_read_unknown_id_is_404_for_owner() -> None:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        read = client.get("/api/v1/router/management/jobs/deadbeef0000")
        assert read.status_code == 404


# --------------------------------------------------------------------------- #
# M3 — raw exception leakage                                                  #
# --------------------------------------------------------------------------- #


def test_chat_error_does_not_leak_exception_details() -> None:
    with _chat_app() as client:
        response = client.post(
            "/api/v1/chat", json={"session_id": "s", "message": "hello"}
        )
    assert response.status_code == 502
    body = response.json()
    assert _SENTINEL not in json.dumps(body)
    assert body["detail"] == (
        "The AI request failed. Check the provider configuration and try again."
    )


def test_chat_stream_error_does_not_leak_exception_details() -> None:
    with _chat_app() as client, client.stream(
        "POST", "/api/v1/chat/stream", json={"session_id": "s", "message": "hello"}
    ) as response:
        text = response.read().decode()
    assert _SENTINEL not in text
    assert "The AI stream failed. Check the provider configuration and try again." in text


def test_no_provider_error_is_stable() -> None:
    """NoChatProviderError keeps its designed guidance message (no internals)."""
    with _chat_app(ProviderManager({})) as client:
        response = client.post(
            "/api/v1/chat", json={"session_id": "s", "message": "hello"}
        )
    assert response.status_code == 503
    body = response.json()
    assert _SENTINEL not in json.dumps(body)
    assert "No provider" in body["detail"]


# --------------------------------------------------------------------------- #
# L1/L5 — Cache-Control on sensitive reads                                    #
# --------------------------------------------------------------------------- #


def test_sensitive_reads_are_no_store() -> None:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        for path in (
            "/api/v1/router/status",
            "/api/v1/dashboard/latest",
            "/api/v1/chat/history?session_id=default",
            "/api/v1/router/info",
            "/api/v1/router/connections",
        ):
            response = client.get(path)
            assert response.status_code == 200, (path, response.status_code)
            assert response.headers.get("cache-control") == "no-store", path


def test_management_reads_are_no_store() -> None:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        for path in (
            "/api/v1/router/management/system",
            "/api/v1/router/management/logs",
            "/api/v1/router/management/packages",
        ):
            # Management reads may 503 when no router is configured; that is
            # fine — the cache-control header must still be no-store.
            response = client.get(path)
            assert response.headers.get("cache-control") == "no-store", path


def test_sse_keeps_no_cache_directive() -> None:
    """The chat SSE stream preserves its own ``no-cache`` header (the no-store
    middleware must not override an existing cache directive)."""
    with _chat_app() as client, client.stream(
        "POST", "/api/v1/chat/stream", json={"session_id": "s", "message": "hello"}
    ) as response:
        assert response.headers.get("cache-control") == "no-cache"


def test_public_endpoints_are_not_no_store() -> None:
    app = create_app()
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200
        assert response.headers.get("cache-control") != "no-store"
