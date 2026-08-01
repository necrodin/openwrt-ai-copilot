"""Live dashboard endpoints.

``GET /dashboard/latest`` returns the most recent snapshot update (useful for
initial page load and fallback when WebSockets are unavailable).

``WS /dashboard/ws`` streams ``DashboardUpdate`` frames in real time: one frame
per poll, plus the latest frame immediately upon connect.
"""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect

from app.core.config import settings
from app.services.snapshot_service import SnapshotService

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/latest")
def dashboard_latest(request: Request) -> dict:
    """Return the latest dashboard update, or a placeholder when empty."""
    service: SnapshotService = request.app.state.snapshot_service
    update = service.latest()
    if update is None:
        return {
            "type": "update",
            "sequence": 0,
            "sent_at": None,
            "source": service.source,
            "device_id": settings.router_device_host or "demo-router",
            "connected": False,
            "error": "no snapshot collected yet",
            "snapshot": None,
        }
    return update.model_dump(mode="json")


@router.websocket("/dashboard/ws")
async def dashboard_ws(websocket: WebSocket) -> None:
    """Stream dashboard updates to the connected client."""
    service: SnapshotService = websocket.app.state.snapshot_service
    await websocket.accept()
    queue = service.subscribe()
    latest = service.latest()
    if latest is not None:
        await websocket.send_text(json.dumps(latest.model_dump(mode="json")))
    try:
        while True:
            update = await queue.get()
            await websocket.send_text(json.dumps(update.model_dump(mode="json")))
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        service.unsubscribe(queue)
