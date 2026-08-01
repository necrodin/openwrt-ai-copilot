"""Live dashboard snapshot service.

Periodically collects a :class:`DeviceSnapshot` from the configured router
(SSH, local, or simulated) on a background asyncio task and fans it out to every
subscribed WebSocket queue as a :class:`DashboardUpdate`. Blocking collection
runs in a worker thread so the event loop is never stalled.

If the device is unreachable the previous good snapshot is retained and
``connected`` is set to ``False``; polling continues so recovery is automatic.
"""

from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import settings
from app.schemas.dashboard import DashboardUpdate
from app.services.demo_source import build_simulated_snapshot
from router_agent.collectors import select_collectors
from router_agent.collectors.base import CollectorContext
from router_agent.config import AgentConfig
from router_agent.model import DeviceSnapshot
from router_agent.snapshot import build_snapshot
from router_agent.transport.base import CommandRunner
from router_agent.transport.local import LocalTransport
from router_agent.transport.ssh import SSHTransport
from router_agent.transport.ubus import UbusClient

logger = logging.getLogger(__name__)

Source = str  # "ssh" | "local" | "simulated"

_SOURCES = {"ssh", "local", "simulated"}


def resolve_source() -> Source:
    """Choose the collection source from settings (empty = smart default)."""
    if settings.router_device_transport:
        return settings.router_device_transport
    return "ssh" if settings.router_device_host else "simulated"


class SnapshotService:
    """Collects router snapshots and broadcasts them to WebSocket subscribers."""

    def __init__(self, *, interval: float | None = None, source: Source | None = None) -> None:
        self._interval = interval if interval is not None else settings.router_poll_interval
        self._source = (source if source is not None else resolve_source()) or "simulated"
        if self._source not in _SOURCES:
            self._source = "simulated"
        self._subscribers: set[asyncio.Queue[DashboardUpdate]] = set()
        self._latest: DashboardUpdate | None = None
        self._task: asyncio.Task[None] | None = None
        self._sequence = 0
        self._device_id = settings.router_device_host or "demo-router"

    # -- lifecycle --------------------------------------------------------- #

    def start(self) -> None:
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._run(), name="dashboard-snapshot")

    async def stop(self) -> None:
        task, self._task = self._task, None
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
        for queue in list(self._subscribers):
            self._send(queue, self._frame(connected=False, error="service shutting down"))
        self._subscribers.clear()

    # -- public API -------------------------------------------------------- #

    @property
    def source(self) -> Source:
        return self._source

    def latest(self) -> DashboardUpdate | None:
        return self._latest

    def subscribe(self) -> asyncio.Queue[DashboardUpdate]:
        queue: asyncio.Queue[DashboardUpdate] = asyncio.Queue(maxsize=1)
        self._subscribers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[DashboardUpdate]) -> None:
        self._subscribers.discard(queue)

    # -- internals --------------------------------------------------------- #

    async def _run(self) -> None:
        while True:
            started = datetime.now(UTC)
            try:
                update = await asyncio.to_thread(self._collect_once)
            except Exception as exc:  # noqa: BLE001 - keep polling after failures
                logger.exception("Dashboard snapshot collection failed")
                update = self._frame(connected=False, error=str(exc))
            await self._publish(update)
            elapsed = (datetime.now(UTC) - started).total_seconds()
            await asyncio.sleep(max(0.0, self._interval - elapsed))

    def _collect_once(self) -> DashboardUpdate:
        if self._source == "simulated":
            return self._frame(
                connected=True,
                source="simulated",
                device_id=self._device_id,
                snapshot=build_simulated_snapshot(),
            )

        config = AgentConfig(
            device_id=self._device_id,
            host=settings.router_device_host,
            port=settings.router_device_port,
            username=settings.router_username,
            ssh_key_path=Path(settings.router_ssh_key) if settings.router_ssh_key else None,
            password=settings.router_password or None,
            command_timeout=settings.router_poll_interval + 10.0,
        )
        runner: CommandRunner
        if self._source == "local":
            runner = LocalTransport()
            transport = "local"
        else:
            runner = SSHTransport(
                config.host,
                port=config.port,
                username=config.username,
                password=config.password,
                key_path=config.ssh_key_path,
                command_timeout=config.command_timeout,
            )
            transport = "ssh"

        ubus = UbusClient(runner, timeout=config.command_timeout)
        ctx = CollectorContext(runner=runner, ubus=ubus, config=config)
        try:
            snapshot = build_snapshot(
                ctx,
                select_collectors(config),
                device_id=config.device_id or config.host or "unconfigured",
                transport=transport,
                host=config.host,
            )
        finally:
            runner.close()
        return self._frame(
            connected=True,
            source=transport,
            device_id=config.device_id,
            snapshot=snapshot,
        )

    def _frame(
        self,
        *,
        connected: bool,
        source: Source | None = None,
        device_id: str | None = None,
        error: str | None = None,
        snapshot: DeviceSnapshot | None = None,
    ) -> DashboardUpdate:
        if snapshot is None and self._latest is not None:
            snapshot = self._latest.snapshot
        self._sequence += 1
        resolved_source = source or self._source
        resolved_device = device_id or (self._latest.device_id if self._latest else self._device_id)
        self._latest = DashboardUpdate(
            type="update",
            sequence=self._sequence,
            sent_at=datetime.now(UTC),
            source=resolved_source,  # type: ignore[arg-type]
            device_id=resolved_device,
            connected=connected,
            error=error,
            snapshot=snapshot,
        )
        return self._latest

    async def _publish(self, update: DashboardUpdate) -> None:
        for queue in list(self._subscribers):
            self._send(queue, update)

    @staticmethod
    def _send(queue: asyncio.Queue[DashboardUpdate], update: DashboardUpdate) -> None:
        try:
            queue.put_nowait(update)
        except asyncio.QueueFull:
            with suppress(asyncio.QueueEmpty):
                queue.get_nowait()
            queue.put_nowait(update)
