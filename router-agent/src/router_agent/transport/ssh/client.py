"""A single-connection SSH client with retries and automatic reconnects."""

from __future__ import annotations

import asyncio

from router_agent.transport.ssh.config import SSHConfig
from router_agent.transport.ssh.connection import SSHConnection
from router_agent.transport.ssh.errors import (
    ConnectionError as SSHConnectionError,
)
from router_agent.transport.ssh.errors import (
    TimeoutError as SSHTimeoutError,
)
from router_agent.transport.ssh.health import SSHHealth

__all__ = ["SSHClient"]

#: Failures considered transient and worth a retry/reconnect.
_TRANSIENT = (SSHConnectionError, SSHTimeoutError)


class SSHClient:
    """Run commands over one connection, retrying transient failures.

    On a transient connect/command failure the client closes the broken
    connection and reconnects, up to ``config.retry_count`` automatic attempts.
    Authentication and host-key failures are never retried — they surface
    immediately.
    """

    def __init__(self, config: SSHConfig, *, connection: SSHConnection | None = None) -> None:
        self._config = config
        self._connection = connection if connection is not None else SSHConnection(config)

    # -- introspection ------------------------------------------------------ #

    @property
    def config(self) -> SSHConfig:
        return self._config

    @property
    def connection(self) -> SSHConnection:
        return self._connection

    @property
    def connected(self) -> bool:
        return self._connection.connected

    @property
    def backend(self) -> str:
        return self._connection.backend.name

    # -- lifecycle ---------------------------------------------------------- #

    async def connect(self) -> None:
        """Connect, retrying transient failures."""
        last: Exception | None = None
        for attempt in range(self._config.retry_count + 1):
            try:
                await self._connection.connect()
                return
            except _TRANSIENT as exc:
                last = exc
                if attempt < self._config.retry_count:
                    await asyncio.sleep(self._config.retry_delay)
        if last is not None:
            raise last

    async def run(self, command: str, *, timeout: float | None = None) -> str:
        """Run one command, reconnecting on transient failures."""
        last: Exception | None = None
        for attempt in range(self._config.retry_count + 1):
            try:
                if not await self._connection.is_alive():
                    await self._connection.connect()
                return await self._connection.run(command, timeout=timeout)
            except _TRANSIENT as exc:
                last = exc
                await self._connection.close()
                if attempt < self._config.retry_count:
                    await asyncio.sleep(self._config.retry_delay)
        if last is not None:
            raise last

    async def health(self) -> SSHHealth:
        return await self._connection.validate()

    async def close(self) -> None:
        await self._connection.close()
