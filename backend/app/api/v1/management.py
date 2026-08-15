"""Router management endpoints.

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
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.auth import (
    SCOPE_DEVICES_WRITE,
    AuthPrincipal,
    require_read,
    require_write,
)
from app.services.router_management import (
    ManagementJob,
    RouterManagementError,
    RouterManagementService,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["router"])

JOB_KINDS = {
    "action",
    "backup",
    "bundle",
    "restore",
    "firewall",
    "wireless",
    "vpn",
    "dhcp",
    "dns",
    "network",
    "system",
    "packages",
    "storage",
}
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
    hostname: str | None = Field(default=None, max_length=63)
    ip: str | None = Field(default=None, max_length=64)
    mac: str | None = Field(default=None, max_length=32)
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=16)
    notes: str | None = Field(default=None, max_length=512)
    name: str | None = Field(default=None, max_length=128)
    target: str | None = Field(default=None, max_length=512)
    server: str | None = Field(default=None, max_length=253)


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


@router.post("/router/management/packages/refresh", dependencies=[Depends(require_write)])
def refresh_packages(request: Request) -> dict:
    """Force a fresh package inventory (bypassing the short TTL cache)."""
    try:
        return _service(request).packages(refresh=True)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/packages/feeds")
def package_feeds(request: Request) -> dict:
    """Return the configured package feeds and last list-update time."""
    try:
        return _service(request).feeds()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/packages/search")
def search_packages(request: Request, q: str = "") -> dict:
    """Search the repository for available packages by name or description."""
    try:
        return _service(request).search_packages(q)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/packages/{name}")
def package_details(request: Request, name: str) -> dict:
    """Return detailed metadata for a single package."""
    try:
        return _service(request).package_details(name)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/storage")
def storage(request: Request) -> dict:
    """Return block devices, filesystem usage and mount information."""
    try:
        return _service(request).storage()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/services")
def services_index(request: Request) -> dict:
    """Return the full service inventory (procd/ubus or init.d fallback)."""
    try:
        return _service(request).services()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/firewall")
def firewall_config(request: Request) -> dict:
    """Return the complete firewall configuration (zones, rules, forwards)."""
    try:
        return _service(request).firewall()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/dns")
def dns_config(request: Request) -> dict:
    """Return the DNS/forwarder configuration (servers, hosts, domain)."""
    try:
        return _service(request).collect_dns()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _job_owners(request: Request) -> dict[str, str]:
    """Per-application map of ``job_id -> creating principal subject``.

    Jobs are in-memory (``ManagementJobStore``); ownership is tracked here in
    the API layer so a read-only principal can never read another principal's
    job result. Initialized once in ``create_app``.
    """
    owners = getattr(request.app.state, "management_job_owners", None)
    if owners is None:
        owners = {}
        request.app.state.management_job_owners = owners
    return owners


def _create_job(
    request: Request,
    service: RouterManagementService,
    principal: AuthPrincipal,
    kind: str,
    message: str = "Queued",
) -> ManagementJob:
    """Create a management job and record its creating principal."""
    job = service.job_store.create(kind, message=message)
    _job_owners(request)[job.id] = principal.subject
    return job


def _run_service_action(
    request: Request,
    service: str,
    action: str,
    principal: AuthPrincipal,
) -> dict:
    """Queue a service action as a tracked job and return it for polling."""
    mgmt = _service(request)
    job = _create_job(request, mgmt, principal, "services", message="Queued")
    asyncio.create_task(
        asyncio.to_thread(mgmt.run_services_job, job.id, action=action, service=service)
    )
    return _job_dict(job)


@router.post("/router/management/services/{service}/start", dependencies=[Depends(require_write)])
def service_start(
    request: Request,
    service: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Start a service and return the tracked job."""
    return _run_service_action(request, service, "start", principal)


@router.post("/router/management/services/{service}/stop", dependencies=[Depends(require_write)])
def service_stop(
    request: Request,
    service: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Stop a running service and return the tracked job."""
    return _run_service_action(request, service, "stop", principal)


@router.post("/router/management/services/{service}/restart", dependencies=[Depends(require_write)])
def service_restart(
    request: Request,
    service: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Restart a service and return the tracked job."""
    return _run_service_action(request, service, "restart", principal)


@router.post("/router/management/services/{service}/enable", dependencies=[Depends(require_write)])
def service_enable(
    request: Request,
    service: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Mark a service to start at boot and return the tracked job."""
    return _run_service_action(request, service, "enable", principal)


@router.post("/router/management/services/{service}/disable", dependencies=[Depends(require_write)])
def service_disable(
    request: Request,
    service: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Prevent a service from starting at boot and return the tracked job."""
    return _run_service_action(request, service, "disable", principal)


@router.get("/router/management/logs")
def logs(request: Request, lines: int = 500) -> dict:
    """Return recent system log entries collected via ``logread``."""
    try:
        return _service(request).read_logs(lines=lines)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/processes")
def processes(request: Request) -> dict:
    """Return a live process table with CPU/memory percentages."""
    try:
        return _service(request).processes()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/router/management/processes/{pid}/kill", dependencies=[Depends(require_write)])
def kill_process(request: Request, pid: int) -> dict:
    """Send SIGTERM to a running process."""
    try:
        return _service(request).kill_process(pid=pid)
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/router/management/system")
def system_info(request: Request) -> dict:
    """Return a read-only snapshot of the router's system configuration."""
    try:
        return _service(request).system_info()
    except RouterManagementError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/router/management/jobs", dependencies=[Depends(require_write)])
async def create_job(
    request: Request,
    payload: ManagementJobRequest,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
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
        job = _create_job(request, service, principal, "action", message="Queued")
        asyncio.create_task(asyncio.to_thread(service.run_action_job, job.id, payload.action))
        return _job_dict(job)

    if payload.kind == "backup":
        job = _create_job(request, service, principal, "backup", message="Queued")
        asyncio.create_task(asyncio.to_thread(service.run_backup_job, job.id))
        return _job_dict(job)

    if payload.kind == "firewall":
        # Explicit actions (restart / reload / enable / disable and section
        # toggles) through the generic firewall job; a bare section toggle falls
        # back to rule enable/disable for backward compatibility.
        action = payload.action
        if payload.action is None:
            action = "enable-rule" if payload.enabled else "disable-rule"
        section_toggles = {
            "enable-rule",
            "disable-rule",
            "enable-zone",
            "disable-zone",
            "enable-forwarding",
            "disable-forwarding",
        }
        if action in section_toggles and not payload.section:
            raise HTTPException(status_code=422, detail="A firewall section is required.")
        resettable_actions = {"restart", "reload", "enable", "disable", *section_toggles}
        if action in resettable_actions and not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change "
                    "the firewall configuration on the router."
                ),
            )
        job = _create_job(request, service, principal, "firewall", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_firewall_job,
                job.id,
                action=action,
                section=payload.section,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "wireless":
        if not payload.action:
            action = f"{'enable' if payload.enabled else 'disable'}-ssid"
        else:
            action = payload.action
        TOGGLE_ACTIONS = ("enable-ssid", "disable-ssid", "enable-radio", "disable-radio")
        if action in TOGGLE_ACTIONS and not payload.section:
            raise HTTPException(status_code=422, detail="A wireless section is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change the "
                    "wireless network on the router."
                ),
            )
        job = _create_job(request, service, principal, "wireless", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_wireless_job,
                job.id,
                action=action,
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
        job = _create_job(request, service, principal, "vpn", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_vpn_toggle_job,
                job.id,
                section=payload.section,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "dhcp":
        if not payload.action:
            raise HTTPException(status_code=422, detail="A DHCP action is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change "
                    "the DHCP configuration on the router."
                ),
            )
        job = _create_job(request, service, principal, "dhcp", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_dhcp_job,
                job.id,
                action=payload.action,
                section=payload.section,
                enabled=payload.enabled,
                hostname=payload.hostname,
                ip=payload.ip,
                mac=payload.mac,
            )
        )
        return _job_dict(job)

    if payload.kind == "dns":
        if not payload.action:
            raise HTTPException(status_code=422, detail="A DNS action is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change "
                    "the DNS configuration on the router."
                ),
            )
        job = _create_job(request, service, principal, "dns", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_dns_job,
                job.id,
                action=payload.action,
                server=payload.server,
                hostname=payload.hostname,
                ip=payload.ip,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "network":
        if not payload.action:
            raise HTTPException(status_code=422, detail="A network action is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to change "
                    "the network on the router."
                ),
            )
        job = _create_job(request, service, principal, "network", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_network_job,
                job.id,
                action=payload.action,
                section=payload.section,
                enabled=payload.enabled,
            )
        )
        return _job_dict(job)

    if payload.kind == "bundle":
        job = _create_job(request, service, principal, "bundle", message="Queued")
        asyncio.create_task(asyncio.to_thread(service.run_bundle_job, job.id))
        return _job_dict(job)

    if payload.kind == "packages":
        if not payload.action:
            raise HTTPException(status_code=422, detail="A package action is required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to run the "
                    f"'{payload.action}' package operation on the router."
                ),
            )
        job = _create_job(request, service, principal, "packages", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_packages_job,
                job.id,
                action=payload.action,
                name=payload.name,
            )
        )
        return _job_dict(job)

    if payload.kind == "system":
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to save "
                    "system settings on the router."
                ),
            )
        job = _create_job(request, service, principal, "system", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_system_job,
                job.id,
                action=payload.action or "save-config",
                hostname=payload.hostname,
                timezone=payload.timezone,
                language=payload.language,
                notes=payload.notes,
            )
        )
        return _job_dict(job)

    if payload.kind == "storage":
        if not payload.action or not payload.target:
            raise HTTPException(status_code=422, detail="A storage action and target are required.")
        if not payload.confirmed:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Confirmation required: send confirmed=true to run the "
                    f"'{payload.action}' storage operation on the router."
                ),
            )
        job = _create_job(request, service, principal, "storage", message="Queued")
        asyncio.create_task(
            asyncio.to_thread(
                service.run_storage_job,
                job.id,
                action=payload.action,
                target=payload.target,
            )
        )
        return _job_dict(job)

    # restore
    if not payload.filename or not payload.content_b64:
        raise HTTPException(status_code=422, detail="filename and content_b64 are required.")
    job = _create_job(request, service, principal, "restore", message="Queued")
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
def get_job(
    request: Request,
    job_id: str,
    principal: Annotated[AuthPrincipal, Depends(require_read)],
) -> dict:
    """Return a management job's current state and result.

    Job results may contain command output, so reads are scoped: the caller
    must hold write scope (admin) or be the principal that created the job.
    Any other caller gets 404 so a job's existence is never revealed.
    """
    job = _service(request).job_store.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    owned = _job_owners(request).get(job_id) == principal.subject
    if not principal.has_scope(SCOPE_DEVICES_WRITE) and not owned:
        raise HTTPException(status_code=404, detail="Job not found")
    return _job_dict(job)


@router.post("/router/management/jobs/{job_id}/confirm", dependencies=[Depends(require_write)])
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


@router.get("/router/management/jobs/{job_id}/artifact", dependencies=[Depends(require_write)])
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
