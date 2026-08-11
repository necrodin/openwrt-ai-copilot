"""Onboarding endpoints: connect, detect, and save a real router.

``POST /router/test-connection``  — verify SSH credentials answer.
``POST /router/detect``           — identify the device (model, firmware, host).
``POST /router/save``             — persist the router (upsert) + start the feed.
``GET /router/connections``       — list previously saved routers.

Saving is an upsert: re-running the wizard for an existing router updates its
record (including a changed IP) instead of inserting a duplicate, and the live
snapshot feed, the router chat caches, and the management inventory caches are
all invalidated so nothing serves data collected from the previous device.
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


def _invalidate_after_connection_change(request: Request) -> None:
    """Clear router chat caches and the management inventory caches.

    Called whenever the active connection changes so neither the chat pipeline
    nor the package console can serve data collected from a previous router.
    """
    manager = getattr(request.app.state, "router_manager", None)
    if manager is not None:
        manager.invalidate()
    management = getattr(request.app.state, "management_service", None)
    if management is not None:
        management.invalidate_caches()


def _apply_connection(request: Request, connection: RouterConnection) -> SnapshotService:
    """Re-point the live snapshot feed at ``connection`` and restart it."""
    service: SnapshotService = request.app.state.snapshot_service
    service.configure_connection(connection)
    service.start()
    return service


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
    """Persist the router (upserting an existing record) and switch the feed.

    ``router_id`` targets an existing saved router; when omitted, the most
    recently saved router is updated if one exists (or a new record created for
    a first-time onboard). This keeps re-onboarding / IP changes from creating
    duplicate connection rows.
    """
    try:
        record, created = router_store.upsert(
            router_id=payload.router_id,
            name=payload.name,
            host=payload.host,
            port=payload.port,
            username=payload.username,
            auth_type=payload.auth_type,
            password=payload.password,
            private_key=payload.private_key,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    connection = RouterConnection(
        host=payload.host,
        port=payload.port,
        username=payload.username,
        password=payload.password,
        private_key=payload.private_key,
        device_id=record.device_id,
    )
    _apply_connection(request, connection)
    _invalidate_after_connection_change(request)
    verb = "Saved" if created else "Updated"
    logger.info(
        "%s router %r (%s) and switched snapshot feed to SSH",
        verb,
        payload.name,
        payload.host,
    )
    return {**router_store.to_public_dict(record), "message": _ROUTER_CONNECTED_HINT}


@router.get("/router/connections")
async def list_connections() -> dict:
    """Return the saved router connections (secrets never included)."""
    records = router_store.get_all()
    return {"routers": [router_store.to_public_dict(record) for record in records]}


@router.delete("/router/connections/{router_id}", dependencies=[Depends(require_write)])
async def delete_connection(request: Request, router_id: int) -> dict:
    """Remove a saved router connection.

    When the deleted record is the router the live feed is currently pointed
    at, the active connection is cleared so the feed stops polling it and
    every subscriber immediately receives a disconnected frame (stale
    snapshots are never served for a removed router).
    """
    records = router_store.get_all()
    match = next((record for record in records if record.id == router_id), None)
    if match is None:
        raise HTTPException(status_code=404, detail="Router connection not found")
    router_store.delete(router_id)
    service: SnapshotService = request.app.state.snapshot_service
    active = service.active_connection
    if active is not None and (
        active.host == match.host and active.username == match.username
    ):
        service.clear_connection(reason=f"Router connection '{match.name}' was deleted")
    _invalidate_after_connection_change(request)
    return {"ok": True}
