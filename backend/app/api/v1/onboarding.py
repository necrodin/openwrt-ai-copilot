"""Onboarding endpoints: connect, detect, and save a real router.

``POST /router/test-connection``  — verify SSH credentials answer.
``POST /router/detect``           — identify the device (model, firmware, host).
``POST /router/save``             — persist the router and start the live feed.
``GET /router/connections``       — list previously saved routers.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.auth import require_write
from app.db.router_store import store as router_store
from app.schemas.onboarding import RouterSaveRequest, RouterTestRequest
from app.services import onboarding as onboarding_service
from app.services.snapshot_service import RouterConnection, SnapshotService

logger = logging.getLogger(__name__)

router = APIRouter(tags=["onboarding"])

_ROUTER_CONNECTED_HINT = (
    "The router was saved but the live feed could not be started yet; "
    "it will connect on the next poll."
)


def _credentials(payload: RouterTestRequest) -> dict:
    return {
        "host": payload.host,
        "port": payload.port,
        "username": payload.username,
        "password": payload.password,
        "private_key": payload.private_key,
    }


@router.post("/router/test-connection")
async def test_connection(payload: RouterTestRequest) -> dict:
    """Try an SSH connection and report whether the device answers."""
    try:
        return await asyncio.to_thread(onboarding_service.probe_connection, **_credentials(payload))
    except Exception as exc:  # noqa: BLE001 - report friendly errors to the UI
        return {"ok": False, "error": onboarding_service.friendly_error(exc)}


@router.post("/router/detect")
async def detect(payload: RouterTestRequest) -> dict:
    """Connect and identify the OpenWrt device (model, firmware, hostname)."""
    try:
        return await asyncio.to_thread(onboarding_service.detect_device, **_credentials(payload))
    except onboarding_service.DeviceDetectionError as exc:
        return {"ok": False, "error": str(exc)}
    except Exception as exc:  # noqa: BLE001 - report friendly errors to the UI
        return {"ok": False, "error": onboarding_service.friendly_error(exc)}


@router.post("/router/save", dependencies=[Depends(require_write)])
async def save(request: Request, payload: RouterSaveRequest) -> dict:
    """Persist the router and switch the live snapshot feed to it."""
    record = router_store.save(
        name=payload.name,
        host=payload.host,
        port=payload.port,
        username=payload.username,
        auth_type=payload.auth_type,
        password=payload.password,
        private_key=payload.private_key,
    )
    connection = RouterConnection(
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        private_key=payload.private_key,
        device_id=record.device_id,
    )
    service: SnapshotService = request.app.state.snapshot_service
    service.configure_connection(connection)
    service.start()
    logger.info(
        "Saved router %r (%s) and switched snapshot feed to SSH", payload.name, payload.host
    )
    return {**router_store.to_public_dict(record), "message": _ROUTER_CONNECTED_HINT}


@router.get("/router/connections")
async def list_connections() -> dict:
    """Return the saved router connections (secrets never included)."""
    records = router_store.get_all()
    return {"routers": [router_store.to_public_dict(record) for record in records]}


@router.delete("/router/connections/{router_id}", dependencies=[Depends(require_write)])
async def delete_connection(router_id: int) -> dict:
    """Remove a saved router connection."""
    records = router_store.get_all()
    match = next((record for record in records if record.id == router_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Router connection not found")
    router_store.delete(router_id)
    return {"ok": True}
