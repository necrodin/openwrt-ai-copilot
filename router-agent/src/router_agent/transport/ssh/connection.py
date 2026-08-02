"""A single managed SSH connection."""

from __future__ import annotations

import time
from contextlib import suppress

from router_agent.transport.ssh.backends import SSHBackend, build_backend
from router_agent.transport.ssh.config import SSHConfig
from router_agent.transport.ssh.health import SSHHealth

__all__ = ["SSHConnection", "DEFAULT_PROBE"]


#: Command used to validate a live connection (trivial, stateless, safe).
DEFAULT_PROBE = "echo ok"


class SSHConnection:
    """One SSH session plus its liveness/validation helpers.

    Wraps a single :class:`~router_agent.transport.ssh.backends.SSHBackend` and
    owns the open/close lifecycle. Use :class:`SSHClient` for retries and
    reconnects, or :class:`SSHConnectionPool` for concurrency.
    """

    def __init__(self, config: SSHConfig, *, backend: SSHBackend | None = None) -> None:
        self._config = config
        self._backend = backend if backend is not None else build_backend(config)
        self._connected = False

    # -- introspection ------------------------------------------------------ #

    @property
    def config(self) -> SSHConfig:
        return self._config

    @property
    def backend(self) -> SSHBackend:
        return self._backend

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def host(self) -> str:
        return self._config.host

    @property
    def port(self) -> int:
        return self._config.port

    # -- lifecycle ---------------------------------------------------------- #

    async def connect(self) -> None:
        if self._connected and await self._backend.is_alive():
            return
        await self._backend.connect()
        self._connected = True

    async def run(self, command: str, *, timeout: float | None = None) -> str:
        return await self._backend.run(
            command, timeout=timeout if timeout is not None else self._config.command_timeout
        )

    async def is_alive(self) -> bool:
        return self._connected and await self._backend.is_alive()

    async def close(self) -> None:
        if self._connected:
            with suppress(Exception):  # noqa: BLE001 - closing best effort
                await self._backend.close()
            self._connected = False

    # -- validation --------------------------------------------------------- #

    async def validate(self, *, probe: str = DEFAULT_PROBE) -> SSHHealth:
        """Probe the connection and return an :class:`SSHHealth` result.

        Never raises: connectivity problems are reported through the returned
        health object.
        """
        backend = self._backend
        started = time.perf_counter()
        try:
            if not await backend.is_alive():
                return SSHHealth.failure(
                    host=self._config.host,
                    port=self._config.port,
                    backend=backend.name,
                    error="connection is not open",
                )
            output = await backend.run(probe, timeout=self._config.command_timeout)
            latency_ms = (time.perf_counter() - started) * 1000.0
            return SSHHealth.success(
                host=self._config.host,
                port=self._config.port,
                backend=backend.name,
                latency_ms=latency_ms,
                probe=probe,
                probe_output=output,
            )
        except Exception as exc:  # noqa: BLE001 - health never raises
            latency_ms = (time.perf_counter() - started) * 1000.0
            return SSHHealth.failure(
                host=self._config.host,
                port=self._config.port,
                backend=backend.name,
                error=str(exc),
                connected=await backend.is_alive(),
                latency_ms=latency_ms,
            )
