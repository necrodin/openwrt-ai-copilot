"""Router API tests: /router/info, /router/status, /router/context, and context service."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Literal

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.demo_source import build_simulated_snapshot
from app.services.router_context import build_context
from tests.auth import admin_headers


def _canned_update(
    *,
    sequence: int = 1,
    source: Literal["ssh", "local", "simulated"] = "simulated",
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
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        app.state.snapshot_service = service
        yield client


# ── /router/info ───────────────────────────────────────────────────────────────


def test_router_info_empty() -> None:
    with client_with_service(FakeSnapshotService(update=None)) as client:
        response = client.get("/api/v1/router/info")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["source"] == "simulated"
    assert body["data"] is None


def test_router_info_with_snapshot() -> None:
    service = FakeSnapshotService(update=_canned_update())
    with client_with_service(service) as client:
        response = client.get("/api/v1/router/info")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["source"] == "simulated"
    assert body["device_id"] == "demo-router"
    assert body["last_updated"] is not None
    data = body["data"]
    assert data is not None
    assert "model" in data
    assert data["cpu"] is not None
    assert isinstance(data["cpu"]["usage_percent"], (int, float, type(None)))
    assert data["memory"]["total_kb"] > 0
    assert len(data["storage"]) > 0
    assert data["storage"][0]["mountpoint"] == "/"
    assert len(data["network_interfaces"]) > 0


def test_router_info_offline_snapshot() -> None:
    update = _canned_update()
    update.connected = False
    update.error = "connection timed out"
    service = FakeSnapshotService(update=update)
    with client_with_service(service) as client:
        response = client.get("/api/v1/router/info")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["data"] is not None
    assert body["data"]["hostname"] != "unknown"


# ── /router/status ────────────────────────────────────────────────────────────


def test_router_status_empty() -> None:
    with client_with_service(FakeSnapshotService(update=None)) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["source"] == "simulated"
    assert body["last_snapshot_at"] is None
    assert body["sequence"] == 0
    assert body["server_time"] is not None


def test_router_status_with_snapshot() -> None:
    service = FakeSnapshotService(update=_canned_update(sequence=42))
    with client_with_service(service) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is True
    assert body["sequence"] == 42
    assert body["last_snapshot_at"] is not None
    assert body["error"] is None
    assert body["server_time"] is not None


def test_router_status_reports_error() -> None:
    update = _canned_update()
    update.connected = False
    update.error = "ssh auth failure"
    service = FakeSnapshotService(update=update)
    with client_with_service(service) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["connected"] is False
    assert body["error"] == "ssh auth failure"


# ── /router/context ───────────────────────────────────────────────────────────


def test_router_context_empty() -> None:
    with client_with_service(FakeSnapshotService(update=None)) as client:
        response = client.get("/api/v1/router/context")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is False
    assert body["router_info"] is None
    assert body["markdown"] is not None
    assert "No router data" in body["markdown"]


def test_router_context_with_snapshot() -> None:
    service = FakeSnapshotService(update=_canned_update())
    with client_with_service(service) as client:
        response = client.get("/api/v1/router/context")
    assert response.status_code == 200
    body = response.json()
    assert body["available"] is True
    assert body["collected_at"] is not None
    assert body["router_info"] is not None
    assert body["router_info"]["hostname"] != "unknown"
    assert body["router_info"]["model"] is not None
    assert body["system_load"] is not None
    assert body["system_load"]["cores"] > 0
    assert body["memory_summary"]["total_kb"] > 0
    assert "used_percent" in body["memory_summary"]
    assert len(body["storage_summary"]) > 0
    assert len(body["network_summary"]) > 0
    assert body["wifi_summary"]["client_count"] > 0
    assert body["raw_snapshot"] is not None
    assert body["markdown"] is not None
    assert "## Router:" in body["markdown"]
    assert "## System Health" in body["markdown"]
    assert "## Storage" in body["markdown"]
    assert "## WiFi" in body["markdown"]


# ── build_context unit tests ──────────────────────────────────────────────────


def test_build_context_none() -> None:
    result = build_context(None)
    assert result["available"] is False
    assert result["reason"] == "No snapshot data available"
    assert result["router_info"] is None


def test_build_context_no_snapshot() -> None:
    update = DashboardUpdate(
        type="update",
        sequence=0,
        sent_at=datetime.now(UTC),
        source="simulated",
        device_id="",
        connected=False,
        snapshot=None,
    )
    result = build_context(update)
    assert result["available"] is False


def test_build_context_markdown_includes_all_sections() -> None:
    result = build_context(_canned_update())
    assert result["available"] is True
    md = result["markdown"]
    assert "## Router:" in md
    assert "## System Health" in md
    assert "## Storage" in md
    assert "## Network Interfaces" in md
    assert "## WiFi" in md


def test_build_context_raw_snapshot_is_serializable() -> None:
    result = build_context(_canned_update())
    raw = result["raw_snapshot"]
    assert isinstance(raw, dict)
    assert raw["meta"]["device_id"] == "demo-router"


# ── CPU/memory/storage/wifi edge cases ────────────────────────────────────────


def test_build_context_missing_cpu_memory() -> None:
    update = _canned_update()
    assert update.snapshot is not None
    update.snapshot.cpu = None  # type: ignore[assignment]
    update.snapshot.memory = None  # type: ignore[assignment]
    result = build_context(update)
    assert result["available"] is True
    assert result["system_load"]["usage_percent"] is None
    assert result["memory_summary"] == {}


def test_build_context_missing_wifi() -> None:
    update = _canned_update()
    assert update.snapshot is not None
    update.snapshot.wifi.radios = []
    update.snapshot.wifi.clients = []
    result = build_context(update)
    assert result["wifi_summary"]["client_count"] == 0
    assert "WiFi" not in result["markdown"]


def test_build_context_missing_storage() -> None:
    update = _canned_update()
    assert update.snapshot is not None
    update.snapshot.storage = []
    result = build_context(update)
    assert result["storage_summary"] == []
    assert "Storage" not in result["markdown"]


def test_build_context_no_network() -> None:
    update = _canned_update()
    assert update.snapshot is not None
    update.snapshot.network = []
    result = build_context(update)
    assert result["network_summary"] == []
    assert "Network Interfaces" not in result["markdown"]


def test_build_context_format_bytes() -> None:
    from app.services.router_context import _format_bytes

    assert "KB" in _format_bytes(512)
    assert "MB" in _format_bytes(2048)
    assert "GB" in _format_bytes(2 * 1024 * 1024)
    assert _format_bytes(None) == "unknown"


def test_build_context_format_uptime() -> None:
    from app.services.router_context import _format_uptime

    assert "m" in _format_uptime(120)
    assert "h" in _format_uptime(7200)
    assert "d" in _format_uptime(90000)
    assert _format_uptime(None) == "unknown"


@pytest.mark.parametrize(
    "endpoint",
    [
        "/api/v1/router/info",
        "/api/v1/router/status",
        "/api/v1/router/context",
    ],
)
def test_all_router_endpoints_are_registered(endpoint: str) -> None:
    """Quick sanity: each endpoint returns 200 with a valid service behind it."""
    service = FakeSnapshotService(update=_canned_update())
    with client_with_service(service) as client:
        response = client.get(endpoint)
    assert response.status_code == 200
    assert isinstance(response.json(), dict)
