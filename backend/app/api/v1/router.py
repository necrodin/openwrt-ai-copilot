"""Router information and management endpoints.

``GET /router/info`` returns structured information about the connected router
(hostname, model, firmware, kernel, uptime, CPU, memory, filesystem, network).

``GET /router/status`` returns a lightweight connection state summary (online,
source, device id, last snapshot time).

``GET /router/context`` returns a structured AI context document built from the
latest router snapshot (markdown summary + structured sections for use by the
chat pipeline).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request

from app.schemas.dashboard import DashboardUpdate
from app.services.router_context import build_context
from app.services.snapshot_service import SnapshotService

router = APIRouter(tags=["router"])


def _snapshot_fields(update: DashboardUpdate | None) -> dict[str, Any] | None:
    if update is None or update.snapshot is None:
        return None
    snap = update.snapshot
    cpu: dict[str, Any] = {
        "usage_percent": snap.cpu.usage_percent if snap.cpu else None,
        "cores": snap.cpu.cores if snap.cpu else 0,
        "load_1": snap.cpu.load_1 if snap.cpu else 0,
        "load_5": snap.cpu.load_5 if snap.cpu else 0,
        "load_15": snap.cpu.load_15 if snap.cpu else 0,
        "uptime_seconds": snap.cpu.uptime_seconds if snap.cpu else 0,
    }
    memory: dict[str, Any] = {
        "total_kb": snap.memory.total_kb if snap.memory else 0,
        "used_kb": snap.memory.used_kb if snap.memory else 0,
        "free_kb": snap.memory.free_kb if snap.memory else 0,
        "available_kb": snap.memory.available_kb if snap.memory else 0,
    }
    storage: list[dict[str, Any]] = [
        {
            "device": m.device,
            "mountpoint": m.mountpoint,
            "filesystem": m.filesystem,
            "total_bytes": m.total_bytes,
            "used_bytes": m.used_bytes,
            "available_bytes": m.available_bytes,
            "use_percent": m.use_percent,
        }
        for m in snap.storage
    ]
    interfaces: list[dict[str, Any]] = [
        {
            "name": i.name,
            "up": i.up,
            "proto": i.proto,
            "mac": i.mac,
            "link": i.link,
            "speed_mbps": i.speed_mbps,
            "rx_bytes": i.rx_bytes,
            "tx_bytes": i.tx_bytes,
            "addresses": [
                {"address": a.address, "prefix": a.prefix, "family": a.family} for a in i.addresses
            ],
        }
        for i in snap.network
    ]
    return {
        "hostname": snap.kernel.hostname if snap.kernel else snap.meta.host or "unknown",
        "model": snap.kernel.model if snap.kernel else snap.meta.model or "unknown",
        "board": snap.kernel.board if snap.kernel else snap.meta.board or "unknown",
        "firmware_version": snap.kernel.version if snap.kernel else snap.meta.firmware or "unknown",
        "kernel": snap.kernel.kernel if snap.kernel else "unknown",
        "architecture": snap.kernel.architecture if snap.kernel else "unknown",
        "cpu": cpu,
        "memory": memory,
        "storage": storage,
        "network_interfaces": interfaces,
    }


@router.get("/router/info")
def router_info(request: Request) -> dict:
    """Return structured router information."""
    service: SnapshotService = request.app.state.snapshot_service
    update = service.latest()
    data = _snapshot_fields(update)
    connected = update.connected if update else False
    return {
        "connected": connected,
        "source": update.source if update else service.source,
        "device_id": update.device_id if update else "",
        "last_updated": update.sent_at.isoformat() if update and update.sent_at else None,
        "data": data,
    }


@router.get("/router/status")
def router_status(request: Request) -> dict:
    """Lightweight connection status summary."""
    service: SnapshotService = request.app.state.snapshot_service
    latest = service.latest()
    now = datetime.now()
    return {
        "connected": latest.connected if latest else False,
        "source": latest.source if latest else service.source,
        "device_id": latest.device_id if latest else "",
        "last_snapshot_at": latest.sent_at.isoformat() if latest and latest.sent_at else None,
        "sequence": latest.sequence if latest else 0,
        "error": latest.error if latest and latest.error else None,
        "server_time": now.isoformat(),
    }


@router.get("/router/context")
def router_context(request: Request) -> dict:
    """Return AI-ready structured context from the latest router snapshot."""
    service: SnapshotService = request.app.state.snapshot_service
    return build_context(service.latest())
