"""Router status API tests: connection state + snapshot + diagnosis + recommendations.

The ``GET /router/status`` contract merges the original connection-state fields
(``connected``, ``source``, ``device_id``, ``last_snapshot_at``, ``sequence``,
``error``, ``server_time``) with the derived snapshot/diagnosis/recommendations.
These tests lock that contract down for the healthy, disconnected, unavailable,
and malformed-snapshot states and prove the legacy fields stay backward
compatible.
"""

from __future__ import annotations

from contextlib import contextmanager
from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.router_snapshot import RouterSnapshot
from tests.auth import admin_headers

# Legacy connection-state fields that must always be present in the response.
LEGACY_FIELDS = (
    "connected",
    "source",
    "device_id",
    "last_snapshot_at",
    "sequence",
    "error",
    "server_time",
)


class StubSnapshotService:
    """Stand-in snapshot service returning a canned RouterSnapshot."""

    def __init__(self, snapshot: RouterSnapshot | None) -> None:
        self._snapshot = snapshot

    def build(self, executor, session_id, requests) -> RouterSnapshot:
        return self._snapshot


class StubFeedService:
    """Stand-in feed service returning a canned DashboardUpdate."""

    def __init__(self, update: DashboardUpdate | None, *, source: str = "simulated") -> None:
        self._update = update
        self.source = source

    def latest(self) -> DashboardUpdate | None:
        return self._update


def _feed_update(*, connected: bool = True, error: str | None = None) -> DashboardUpdate:
    return DashboardUpdate(
        type="update",
        sequence=1,
        sent_at=datetime.now(UTC),
        source="simulated",
        device_id="demo-router",
        connected=connected,
        error=error,
        snapshot=None,
    )


def _healthy_snapshot() -> RouterSnapshot:
    return RouterSnapshot(
        system={"hostname": "demo-router", "model": "RT-1", "firmware": "23.05"},
        cpu={"usage_percent": 12.0, "cores": 4, "load_1": 0.5},
        memory={"used_percent": 40.0, "total_kb": 262144},
        storage=[{"mountpoint": "/overlay", "use_percent": 30.0}],
        network=[{"name": "wan", "up": True, "proto": "dhcp"}],
        wifi={"radios": ["radio0"], "client_count": 3},
    )


@contextmanager
def _client(snapshot: RouterSnapshot | None, *, connected: bool = True, error: str | None = None):
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        router = (
            None
            if snapshot is None
            else SimpleNamespace(
                router_id="default",
                executor=None,
                snapshot_service=StubSnapshotService(snapshot),
            )
        )
        app.state.router_manager = SimpleNamespace(default=router)
        app.state.snapshot_service = StubFeedService(
            _feed_update(connected=connected, error=error) if snapshot is not None else None
        )
        yield client


def _assert_unavailable(body: dict) -> None:
    """Assert the merged contract for an unavailable router."""
    assert body["snapshot"] is None
    assert body["diagnosis"] == []
    assert body["recommendations"] == []
    assert body["connected"] is False
    assert body["source"] == "simulated"
    assert body["device_id"] == ""
    assert body["last_snapshot_at"] is None
    assert body["sequence"] == 0
    assert body["error"] is None
    assert body["server_time"] is not None


def test_healthy_router() -> None:
    with _client(_healthy_snapshot()) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["system"]["hostname"] == "demo-router"
    assert body["snapshot"]["cpu"]["usage_percent"] == 12.0
    assert body["diagnosis"] == []
    assert body["recommendations"] == []
    assert body["connected"] is True
    assert body["sequence"] == 1
    assert body["error"] is None


def test_unavailable_router() -> None:
    with _client(None) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    _assert_unavailable(response.json())


def test_empty_snapshot_is_unavailable() -> None:
    with _client(RouterSnapshot()) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is None
    assert body["diagnosis"] == []
    assert body["recommendations"] == []
    # the feed is connected but no router data has been derived yet
    assert body["connected"] is True
    assert body["error"] is None


def test_diagnosis_included() -> None:
    snapshot = _healthy_snapshot()
    snapshot = RouterSnapshot(
        system=snapshot.system,
        cpu=snapshot.cpu,
        memory={"used_percent": 95.0, "total_kb": 262144},
        storage=snapshot.storage,
        network=snapshot.network,
        wifi=snapshot.wifi,
    )
    with _client(snapshot) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is not None
    assert body["diagnosis"] != []
    assert body["diagnosis"][0]["severity"] == "critical"
    assert body["diagnosis"][0]["title"] == "Critical memory utilization"


def test_recommendations_included() -> None:
    snapshot = _healthy_snapshot()
    snapshot = RouterSnapshot(
        system=snapshot.system,
        cpu={"usage_percent": 95.0, "cores": 4, "load_1": 8.0},
        memory=snapshot.memory,
        storage=snapshot.storage,
        network=snapshot.network,
        wifi=snapshot.wifi,
    )
    with _client(snapshot) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["recommendations"] != []
    assert body["recommendations"][0]["id"] == "rec-cpu"
    assert body["recommendations"][0]["priority"] == "urgent"
    assert body["recommendations"][0]["action"]


def test_disconnected_router_reports_error_with_retained_snapshot() -> None:
    with _client(_healthy_snapshot(), connected=False, error="ssh auth failure") as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["error"] == "ssh auth failure"
    assert body["snapshot"] is not None
    assert body["snapshot"]["system"]["hostname"] == "demo-router"
    assert body["diagnosis"] == []
    assert body["recommendations"] == []
    assert body["last_snapshot_at"] is not None


def test_malformed_snapshot_is_tolerated() -> None:
    snapshot = RouterSnapshot(
        system={"hostname": "demo-router", "model": "", "firmware": ""},
        cpu={"usage_percent": None, "cores": 0, "load_1": None},
        memory=None,
        storage=[],
        network=[],
        wifi=None,
    )
    with _client(snapshot) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is not None
    titles = [finding["title"] for finding in body["diagnosis"]]
    assert titles == ["Unknown router values"]
    assert body["recommendations"] != []
    assert body["recommendations"][0]["id"] == "rec-data-quality"


def test_legacy_fields_coexist_with_derived_status() -> None:
    with _client(_healthy_snapshot()) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    for field in LEGACY_FIELDS:
        assert field in body
    assert set(LEGACY_FIELDS) <= set(body)
    assert {"snapshot", "diagnosis", "recommendations"} <= set(body)
