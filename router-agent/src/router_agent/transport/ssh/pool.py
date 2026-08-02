"""A bounded pool of reusable SSH connections."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager

from router_agent.transport.ssh.backends import SSHBackend, build_backend
from router_agent.transport.ssh.config import SSHConfig
from router_agent.transport.ssh.connection import SSHConnection
from router_agent.transport.ssh.health import SSHHealth

__all__ = ["SSHConnectionPool", "BackendFactory"]

#: Builds a fresh backend for a new pooled connection.
BackendFactory = Callable[[SSHConfig], SSHBackend]


class SSHConnectionPool:
    """Reuses up to ``config.pool_size`` live connections.

    ``acquire()`` hands out an idle, still-alive connection — reconnecting a
    stale one or opening a new connection when the pool is not yet full — and
    returns it to the idle set on release. With ``validate=True`` each lease is
    probed before being handed out.
    """

    def __init__(self, config: SSHConfig, *, backend_factory: BackendFactory | None = None) -> None:
        self._config = config
        self._factory = backend_factory or build_backend
        self._idle: deque[SSHConnection] = deque()
        self._semaphore: asyncio.Semaphore | None = None
        self._created = 0
        self._closed = False

    # -- accounting --------------------------------------------------------- #

    @property
    def config(self) -> SSHConfig:
        return self._config

    @property
    def size(self) -> int:
        """Connections created so far (idle + leased)."""
        return self._created

    @property
    def idle(self) -> int:
        return len(self._idle)

    @property
    def busy(self) -> int:
        return max(0, self._created - len(self._idle))

    # -- lifecycle ---------------------------------------------------------- #

    def _ensure(self) -> None:
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(self._config.pool_size)

    @asynccontextmanager
    async def acquire(self, *, validate: bool = False) -> AsyncIterator[SSHConnection]:
        """Lease one connection; it is returned on context exit."""
        if self._closed:
            raise RuntimeError("SSH connection pool is closed")
        self._ensure()
        assert self._semaphore is not None
        await self._semaphore.acquire()
        conn: SSHConnection | None = None
        try:
            conn = await self._get_connection(validate=validate)
            yield conn
        finally:
            if conn is not None and not self._closed:
                await self.release(conn)
            else:
                if conn is not None:
                    await conn.close()
                self._semaphore.release()

    async def release(self, conn: SSHConnection) -> None:
        """Return a connection to the idle set (or close it if unusable)."""
        assert self._semaphore is not None
        if await conn.is_alive():
            self._idle.append(conn)
        else:
            await conn.close()
        self._semaphore.release()

    async def _get_connection(self, *, validate: bool) -> SSHConnection:
        while self._idle:
            candidate = self._idle.popleft()
            if await candidate.is_alive():
                if not validate or (await candidate.validate()).ok:
                    return candidate
                await candidate.close()
                continue
            await candidate.close()
        conn = SSHConnection(self._config, backend=self._factory(self._config))
        self._created += 1
        await conn.connect()
        return conn

    async def health(self) -> list[SSHHealth]:
        """Probe every idle connection (used to monitor pool liveness)."""
        return [await conn.validate() for conn in self._idle]

    async def close(self) -> None:
        """Close all idle connections and mark the pool unusable.

        Leased connections are closed when they are returned via ``release``.
        """
        self._closed = True
        while self._idle:
            await self._idle.popleft().close()
