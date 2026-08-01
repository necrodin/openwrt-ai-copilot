"""Dashboard tests: simulated source, snapshot service, REST + WebSocket API."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal

from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.demo_source import build_simulated_snapshot
from app.services.snapshot_service import SnapshotService
from router_agent.model import DeviceSnapshot


def _canned_update(
    *, sequence: int = 1, source: Literal["ssh", "local", "simulated"] = "simulated"
) -> DashboardUpdate:
    return DashboardUpdate(
        type="update",
        sequence=sequence,
        sent_at=datetime.now(UTC),
        source=source,
        device_id="demo-router",
        connected=True,
        snapshot=build_simulated_snapshot(),
    )


class FakeSnapshotService:
    """Minimal stand-in exposing the SnapshotService interface for API tests."""

    def __init__(self, update: DashboardUpdate | None) -> None:
        self.update = update
        self.source = "simulated"
        self.queue: asyncio.Queue[DashboardUpdate] = asyncio.Queue(maxsize=4)

    def latest(self) -> DashboardUpdate | None:
        return self.update

    def subscribe(self) -> asyncio.Queue[DashboardUpdate]:
        return self.queue

    def unsubscribe(self, queue: asyncio.Queue[DashboardUpdate]) -> None:
        pass

    async def stop(self) -> None:
        pass


@contextmanager
def client_with_service(service: FakeSnapshotService) -> Iterator[TestClient]:
    """TestClient whose snapshot service is replaced after lifespan starts."""
    app = create_app()
    with TestClient(app) as client:
        app.state.snapshot_service = service
        yield client


def test_simulated_snapshot_populated() -> None:
    snapshot = build_simulated_snapshot()
    assert isinstance(snapshot, DeviceSnapshot)
    assert snapshot.meta.device_id == "demo-router"
    assert snapshot.cpu is not None and snapshot.cpu.usage_percent is not None
    assert snapshot.memory is not None and snapshot.memory.total_kb > 0
    assert snapshot.temperature and snapshot.temperature[0].temperature_c > 0
    assert snapshot.storage and snapshot.storage[0].mountpoint == "/"
    assert snapshot.network
    assert snapshot.firewall.zones
    assert snapshot.vpn and snapshot.vpn[0].kind == "wireguard"
    assert snapshot.wifi.radios and snapshot.wifi.clients
    assert snapshot.clients
    assert snapshot.routing
    assert snapshot.errors == []


def test_simulated_snapshot_drifts_over_time() -> None:
    first = build_simulated_snapshot()
    second = build_simulated_snapshot()
    assert first.cpu is not None and second.cpu is not None
    assert first.cpu.usage_percent != second.cpu.usage_percent


async def test_snapshot_service_publishes_to_subscribers() -> None:
    service = SnapshotService(interval=0.02, source="simulated")
    service.start()
    queue = service.subscribe()
    try:
        update = await asyncio.wait_for(queue.get(), timeout=3.0)
        assert update.connected is True
        assert update.source == "simulated"
        assert update.snapshot is not None
        assert update.snapshot.meta.device_id == "demo-router"
        assert service.latest() is not None
    finally:
        service.unsubscribe(queue)
        await service.stop()


def test_dashboard_latest_empty() -> None:
    with client_with_service(FakeSnapshotService(update=None)) as client:
        response = client.get("/api/v1/dashboard/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["snapshot"] is None


def test_dashboard_latest_with_update() -> None:
    service = FakeSnapshotService(update=_canned_update())
    with client_with_service(service) as client:
        response = client.get("/api/v1/dashboard/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["sequence"] == 1
    assert body["source"] == "simulated"
    assert body["snapshot"]["meta"]["device_id"] == "demo-router"


def test_dashboard_ws_streams_initial_and_queued_frames() -> None:
    service = FakeSnapshotService(update=_canned_update(sequence=7))
    service.queue.put_nowait(_canned_update(sequence=8))
    with (
        client_with_service(service) as client,
        client.websocket_connect("/api/v1/dashboard/ws") as websocket,
    ):
        first = json.loads(websocket.receive_text())
        second = json.loads(websocket.receive_text())
    assert first["sequence"] == 7
    assert second["sequence"] == 8
    assert first["snapshot"]["meta"]["device_id"] == "demo-router"
