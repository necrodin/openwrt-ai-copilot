"""Router management endpoints (Sprint 31).

Real, SSH-backed administrative operations for the router console:

- ``GET  /router/management/packages`` — installed packages + available upgrades.
- ``POST /router/management/packages/refresh`` — force a fresh inventory.
- ``GET  /router/management/logs`` — recent ``logread`` entries.
- ``POST /router/management/jobs`` — start an action / backup / bundle / restore.
- ``GET  /router/management/jobs/{id}`` — job progress and result.
- ``POST /router/management/jobs/{id}/confirm`` — execute a staged restore.
- ``GET  /router/management/jobs/{id}/artifact`` — download backup/bundle bytes.

All mutating operations run as tracked background jobs and require explicit
confirmation, so the UI can show progress and errors without ever issuing a
destructive command implicitly.
"""

from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.services.router_management import (
    ManagementJob,
    RouterManagementError,
    RouterManagementService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["router"])

JOB_KINDS = {"action", "backup", "bundle", "restore", "firewall", "wireless", "vpn"}
CONFIRMED_KINDS = {"action", "restore"}


class ManagementJobRequest(BaseModel):
    """Payload for starting a management job."""

    kind: str
    action: str | None = Field(default=None, max_length=64)
    confirmed: bool = False
    filename: str | None = Field(default=None, max_length=255)
    content_b64: str | None = Field(default=None, max_length=64_000_000)
    section: str | None = Field(default=None, max_length=128)
    enabled: bool = False


def _service(request: Request) -> RouterManagementService:
    service: RouterManagementService | None = getattr(request.app.state, "management_service", None)
    if service is None:
        raise HTTPException(status_code=503, detail="Router management service is not available.")
    return service


def _job_dict(job: ManagementJob) -> dict:
    return job.to_dict(include_artifact=False)


@router.get("/router/management/packages")
def packages(request: Request, refresh: bool = False) -> dict:
    """Return the installed package inventory and available upgrades."""
    try:
        return _service(request).packages(refresh=refresh)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/router/management/packages/refresh")
def refresh_packages(request: Request) -> dict:
    """Force a fresh package inventory (bypassing the short TTL cache)."""
    try:
        return _service(request).packages(refresh=True)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/logs")
def logs(request: Request, lines: int = 500) -> dict:
    """Return recent system log entries collected via ``logread``."""
    try:
        return _service(request).read_logs(lines=lines)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/router/management/jobs")
async def create_job(request: Request, payload: ManagementJobRequest) -> dict:
    """Start a management job and return it for progress polling."""
    service = _service(request)
    if payload.kind not in JOB_KINDS:
        raise HTTPException(status_code=422, detail=f"Unsupported job kind: {payload.kind}")

    if payload.kind == "action":
        if not payload.action:
            raise HTTPException(status_code=422, detail="An action name is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to execute "
                    f"'{payload.action}' on the router."
                ),
            )
        job = service.job_store.create("action", message="Queued")
        asyncio.create_task(asyncio.to_thread(service.run_action_job, job.id, payload.action))
        return _job_dict(job)

    if payload.kind == "backup":
        job = service.job_store.create("backup", message="Queued")
        asyncio.create_task(asyncio.to_thread(service.run_backup_job, job.id))
        return _job_dict(job)

    if payload.kind == "firewall":
        if not payload.section:
            raise HTTPException(status_code=422, detail="A firewall section is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change the "
                    "firewall rule on the router."
                ),
            )
        job = service.job_store.create("firewall", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_firewall_toggle_job,
                job.id,
                section=payload.section,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "wireless":
        if not payload.section:
            raise HTTPException(status_code=422, detail="A wireless section is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change the "
                    "wireless network on the router."
                ),
            )
        job = service.job_store.create("wireless", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_wireless_toggle_job,
                job.id,
                section=payload.section,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "vpn":
        if not payload.section:
            raise HTTPException(status_code=422, detail="A VPN section is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change the "
                    "VPN instance on the router."
                ),
            )
        job = service.job_store.create("vpn", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_vpn_toggle_job,
                job.id,
                section=payload.section,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "bundle":
        job = service.job_store.create("bundle", message="Queued")
        asyncio.create_task(asyncio.to_thread(service.run_bundle_job, job.id))
        return _job_dict(job)

    # restore
    if not payload.filename or not payload.content_b64:
        raise HTTPException(status_code=422, detail="filename and content_b64 are required.")
    job = service.job_store.create("restore", message="Queued")
    try:
        service.stage_restore_job(
            job.id,
            filename=payload.filename,
            content_b64=payload.content_b64,
        )
    except RouterManagementError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _job_dict(job)


@router.get("/router/management/jobs/{job_id}")
def get_job(request: Request, job_id: str) -> dict:
    """Return a management job's current state and result."""
    job = _service(request).job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job)


@router.post("/router/management/jobs/{job_id}/confirm")
async def confirm_job(request: Request, job_id: str) -> dict:
    """Confirm and execute a staged restore job."""
    service = _service(request)
    job = service.job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.kind != "restore":
        raise HTTPException(status_code=422, detail="Only restore jobs can be confirmed.")
    asyncio.create_task(asyncio.to_thread(service.confirm_restore_job, job.id))
    return _job_dict(job)


@router.get("/router/management/jobs/{job_id}/artifact")
def download_artifact(request: Request, job_id: str) -> Response:
    """Download the artifact (backup or diagnostic bundle) of a finished job."""
    job = _service(request).job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.artifact_bytes is None:
        raise HTTPException(status_code=409, detail="Job has no downloadable artifact yet.")
    filename = job.artifact_name or "download.bin"
    return Response(
        content=job.artifact_bytes,
        media_type=job.artifact_media_type or "application/octet-stream",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )
