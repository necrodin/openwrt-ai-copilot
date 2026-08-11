"""Regression tests for safe re-onboarding and router IP changes.

Covers the "ROUTER IP / RE-ONBOARDING" workstream:

* ``POST /router/save`` is an upsert — re-running the wizard for an existing
  router updates its row (including a changed IP) instead of inserting a
  duplicate connection.
* A changed IP re-points the live snapshot feed and invalidates the router
  chat caches and the management inventory caches.
* Deleting the active router clears the live feed and marks subscribers
  disconnected (stale snapshots are never served for a removed router).
* Background management jobs resolve the *current* connection each time they
  execute, never a cached/stale one.

No real SSH is attempted; verification happens at the persistence + wiring
layer using the throwaway test database.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from app.db.router_store import store as router_store
from app.services import snapshot_service as snapshot_service_module
from app.services.router_context_cache import RouterContextCache
from app.services.router_management import RouterManagementService
from app.services.router_manager import RouterManager
from app.services.router_snapshot import RouterSnapshotService
from app.services.router_tool_executor import RouterToolResult
from app.services.snapshot_service import RouterConnection
from router_agent.model import DeviceSnapshot, SnapshotMeta


@pytest.fixture(autouse=True)
def _clean_routers(client: TestClient) -> None:
    """Tests assume an empty router table; the shared test DB persists per session."""
    for record in router_store.get_all():
        router_store.delete(record.id)
    yield


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


def test_save_without_router_id_updates_most_recent(client: TestClient) -> None:
    first = client.post("/api/v1/router/save", json=_save_payload()).json()
    second = client.post(
        "/api/v1/router/save",
        json=_save_payload(name="Garage", host="10.0.0.5"),
    ).json()

    routers = client.get("/api/v1/router/connections").json()["routers"]
    assert len(routers) == 1
    assert routers[0]["id"] == first["id"] == second["id"]
    assert routers[0]["host"] == "10.0.0.5"
    assert routers[0]["name"] == "Garage"


def test_save_with_router_id_updates_target_not_duplicates(client: TestClient) -> None:
    saved = client.post("/api/v1/router/save", json=_save_payload()).json()

    update = client.post(
        "/api/v1/router/save",
        json=_save_payload(router_id=saved["id"], host="10.0.0.9"),
    ).json()
    assert update["id"] == saved["id"]
    assert update["host"] == "10.0.0.9"

    routers = client.get("/api/v1/router/connections").json()["routers"]
    assert len(routers) == 1
    assert routers[0]["id"] == saved["id"]


def test_save_with_unknown_router_id_is_404(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/save",
        json=_save_payload(router_id=999_999),
    )
    assert response.status_code == 404


def test_save_ip_change_repoints_active_connection(client: TestClient) -> None:
    first = client.post(
        "/api/v1/router/save",
        json=_save_payload(name="Router", host="192.168.1.1"),
    ).json()

    service: snapshot_service_module.SnapshotService = client.app.state.snapshot_service
    assert service.active_connection is not None
    assert service.active_connection.host == "192.168.1.1"

    client.post(
        "/api/v1/router/save",
        json=_save_payload(name="Router", router_id=first["id"], host="192.168.1.42"),
    ).json()

    assert service.active_connection is not None
    assert service.active_connection.host == "192.168.1.42"
    assert service.source == "ssh"
    # a fresh router must not serve a snapshot collected from the old IP
    assert service.latest() is None


def test_save_ip_change_invalidates_management_caches(client: TestClient) -> None:
    saved = client.post("/api/v1/router/save", json=_save_payload()).json()

    management: RouterManagementService = client.app.state.management_service
    assert management._packages_cache == {}
    assert management._opkg_list_text == ""

    # prime the caches as if a previous invocation had populated them
    management._packages_cache = {"some": "package data"}
    management._packages_cache_at = 1.0
    management._opkg_list_text = "stale opkg list"
    management._opkg_list_at = 1.0

    client.post(
        "/api/v1/router/save",
        json=_save_payload(router_id=saved["id"], host="192.168.1.42"),
    ).json()

    assert management._packages_cache == {}
    assert management._packages_cache_at == 0.0
    assert management._opkg_list_text == ""
    assert management._opkg_list_at == 0.0


def test_router_manager_invalidate_clears_cached_context() -> None:
    manager = RouterManager()
    registered = manager.register("test-router", router_tool=None)

    result = RouterToolResult(name="system", ok=True, result={"hostname": "test"})
    registered.cache.set("session-1", "system", result)
    assert registered.cache.get("session-1", "system") is not None
    assert registered.snapshot_service._cache.get("session-1", "system") is not None

    manager.invalidate()

    assert registered.cache.get("session-1", "system") is None
    assert registered.snapshot_service._cache.get("session-1", "system") is None


def test_delete_active_router_clears_feed_and_marks_disconnected(client: TestClient) -> None:
    saved = client.post("/api/v1/router/save", json=_save_payload()).json()

    service: snapshot_service_module.SnapshotService = client.app.state.snapshot_service
    # simulate an existing retained snapshot so we can prove it is dropped
    snapshot = DeviceSnapshot(
        meta=SnapshotMeta(collected_at=datetime.now(UTC), host="192.168.1.1")
    )
    service._latest = service._frame(connected=True, snapshot=snapshot)
    assert service.latest() is not None and service.latest().snapshot is not None

    response = client.delete(f"/api/v1/router/connections/{saved['id']}")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

    assert service.active_connection is None
    assert service.source == "none"
    latest = service.latest()
    assert latest is not None
    assert latest.connected is False
    assert latest.snapshot is None
    assert "was deleted" in (latest.error or "")
    assert client.get("/api/v1/router/connections").json() == {"routers": []}


def test_jobs_resolve_current_connection_not_stale() -> None:
    """Background management jobs must look the connection up at execution time."""
    current = None

    def resolve():
        return current

    service = RouterManagementService(resolve_connection=resolve)

    current = RouterConnection(host="10.0.0.1", port=22, username="root")
    first = service.connection()
    assert first.host == "10.0.0.1"

    current = RouterConnection(host="10.0.0.2", port=22, username="root")
    second = service.connection()
    # the resolved connection tracks the live feed; a previously resolved value
    # from the old IP is never returned
    assert second.host == "10.0.0.2"
    assert first is not second


def test_router_snapshot_service_clear_drops_cache() -> None:
    cache = RouterContextCache()
    snapshot_service = RouterSnapshotService(cache)
    result = RouterToolResult(name="system", ok=True, result={"hostname": "test"})
    cache.set("session-1", "system", result)
    assert cache.get("session-1", "system") is not None
    snapshot_service.clear()
    assert cache.get("session-1", "system") is None


def test_router_context_cache_clear_all_drops_entries() -> None:
    cache = RouterContextCache()
    cache.set("a", "cpu", RouterToolResult(name="cpu", ok=True, result={}))
    cache.set("b", "cpu", RouterToolResult(name="cpu", ok=True, result={}))
    cache.clear()
    assert cache.stats()["hits"] == 0
    assert cache.get("a", "cpu") is None
    assert cache.get("b", "cpu") is None