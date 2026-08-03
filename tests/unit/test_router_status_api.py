"""Router status API tests: snapshot + diagnosis + recommendations via GET /router/status."""

from __future__ import annotations

from contextlib import contextmanager
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.router_snapshot import RouterSnapshot


class StubSnapshotService:
    """Stand-in snapshot service returning a canned RouterSnapshot."""

    def __init__(self, snapshot: RouterSnapshot | None) -> None:
        self._snapshot = snapshot

    def build(self, executor, session_id, requests) -> RouterSnapshot:
        return self._snapshot


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
def _client(snapshot: RouterSnapshot | None):
    app = create_app()
    with TestClient(app) as client:
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
        yield client


def test_healthy_router() -> None:
    with _client(_healthy_snapshot()) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["system"]["hostname"] == "demo-router"
    assert body["snapshot"]["cpu"]["usage_percent"] == 12.0
    assert body["diagnosis"] == []
    assert body["recommendations"] == []


def test_unavailable_router() -> None:
    with _client(None) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    assert response.json() == {
        "snapshot": None,
        "diagnosis": [],
        "recommendations": [],
    }


def test_empty_snapshot_is_unavailable() -> None:
    with _client(RouterSnapshot()) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    assert response.json() == {
        "snapshot": None,
        "diagnosis": [],
        "recommendations": [],
    }


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
