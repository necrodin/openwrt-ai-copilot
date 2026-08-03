"""Synchronous :class:`SSHTransport` facade for the router agent.

The collectors (and the dashboard) consume the synchronous
:class:`~router_agent.transport.base.CommandRunner` contract — ``run() -> str``
and ``close()``. This facade keeps that contract while delegating to the async
:class:`~router_agent.transport.ssh.client.SSHClient` through a background
event-loop bridge. It also exposes ``arun()`` and ``health()`` for async callers.

Explicit lifecycle is supported via ``connect()``, ``disconnect()``, and
``reconnect()``. State is reported through ``connected`` and ``state`` properties.

Backwards compatibility: the previous constructor signature still works, and a
connect failure raises :class:`ConnectionFailedError` at construction time.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path

from router_agent.errors import ConnectionFailedError
from router_agent.transport.ssh.bridge import EventLoopBridge
from router_agent.transport.ssh.client import SSHClient
from router_agent.transport.ssh.config import SSHConfig, SSHCredentials
from router_agent.transport.ssh.errors import (
    AuthenticationError,
    HostKeyError,
)
from router_agent.transport.ssh.errors import (
    TimeoutError as SSHTimeoutError,
)
from router_agent.transport.ssh.health import SSHHealth

logger = logging.getLogger(__name__)

__all__ = ["SSHTransport", "ConnectionState"]


class ConnectionState:
    """State constants for the SSH transport connection lifecycle."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    FAILED = "failed"


class SSHTransport:
    """Executes commands on a remote OpenWrt device over SSH.

    Uses an internal :class:`SSHClient` (retries, reconnects, keep-alive).

    Lifecycle::

        transport = SSHTransport("192.168.1.1", username="root")
        transport.connect()       # explicit connect (optional - constructor does it)
        transport.run("uptime")
        transport.disconnect()    # graceful disconnect
        transport.reconnect()     # reconnect after disconnect
        transport.close()        # final cleanup (also calls disconnect)
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_path: Path | str | None = None,
        connect_timeout: float = 15.0,
        command_timeout: float = 20.0,
        banner_timeout: float | None = None,  # legacy, folded into connect_timeout
        known_hosts: Path | str | None = None,
        pool_size: int = 4,
        retry_count: int = 2,
        retry_delay: float = 0.5,
        keepalive_interval: float = 30.0,
        host_key_policy: str = "auto",
        private_key: str | None = None,
        private_key_passphrase: str | None = None,
        backend: str | None = None,
        bridge: EventLoopBridge | None = None,
        auto_connect: bool = True,
    ) -> None:
        self._config = SSHConfig(
            host=host,
            port=port,
            timeout=connect_timeout,
            command_timeout=command_timeout,
            keepalive_interval=keepalive_interval,
            pool_size=pool_size,
            retry_count=retry_count,
            retry_delay=retry_delay,
            host_key_policy=host_key_policy,
            known_hosts=Path(known_hosts) if known_hosts else None,
            backend=backend,
            credentials=SSHCredentials(
                username=username,
                password=password,
                private_key=private_key,
                private_key_path=Path(key_path) if key_path else None,
                private_key_passphrase=private_key_passphrase,
            ),
        )
        self._client = SSHClient(self._config)
        self._bridge = bridge if bridge is not None else EventLoopBridge()
        self._owns_bridge = bridge is None
        self._closed = False
        self._state = ConnectionState.DISCONNECTED

        if auto_connect:
            try:
                self.connect()
            except ConnectionFailedError:
                self.close()
                raise

    # -- state -------------------------------------------------------------- #

    @property
    def connected(self) -> bool:
        """True when the underlying connection is active."""
        if self._closed:
            return False
        try:
            return self._bridge.run(self._client.connection.is_alive())
        except Exception:
            return False

    @property
    def state(self) -> str:
        """Current connection lifecycle state."""
        if self._closed:
            return ConnectionState.DISCONNECTED
        return self._state

    @property
    def config(self) -> SSHConfig:
        return self._config

    @property
    def host(self) -> str:
        return self._client.config.host

    @property
    def port(self) -> int:
        return self._client.config.port

    @property
    def backend(self) -> str:
        return self._client.backend

    # -- lifecycle ---------------------------------------------------------- #

    def connect(self) -> None:
        """Open the SSH connection (idempotent if already connected)."""
        if self._closed:
            raise RuntimeError("Cannot connect: transport is closed.")
        if self._state == ConnectionState.CONNECTED and self.connected:
            return
        self._state = ConnectionState.CONNECTING
        logger.info("Connecting to %s:%d (backend=%s)", self.host, self.port, self.backend)
        try:
            self._bridge.run(self._client.connect())
        except (AuthenticationError, HostKeyError):
            self._state = ConnectionState.FAILED
            raise
        except (SSHTimeoutError, OSError) as exc:
            self._state = ConnectionState.FAILED
            raise ConnectionFailedError(f"connect to {self.host} failed: {exc}") from exc
        self._state = ConnectionState.CONNECTED
        logger.info("Connected to %s:%d", self.host, self.port)

    def disconnect(self) -> None:
        """Gracefully close the SSH session while keeping the bridge alive."""
        if self._closed:
            return
        self._state = ConnectionState.DISCONNECTED
        with suppress(Exception):
            self._bridge.run(self._client.close())

    def reconnect(self) -> None:
        """Disconnect and reconnect in a single call."""
        self.disconnect()
        self.connect()

    # -- synchronous CommandRunner contract --------------------------------- #

    def run(self, command: str, *, timeout: float | None = None) -> str:
        """Run a command and return its cleaned stdout (blocking)."""
        return self._bridge.run(self._client.run(command, timeout=timeout))

    def close(self) -> None:
        """Close the connection and stop the bridge (idempotent)."""
        if self._closed:
            return
        self._closed = True
        self._state = ConnectionState.DISCONNECTED
        try:
            self._bridge.run(self._client.close())
        except Exception:
            pass
        finally:
            if self._owns_bridge:
                self._bridge.close()

    # -- async interface ---------------------------------------------------- #

    async def arun(self, command: str, *, timeout: float | None = None) -> str:
        """Run a command from an async caller, returning cleaned stdout."""
        return await self._client.run(command, timeout=timeout)

    def health(self) -> SSHHealth:
        """Probe the connection and return an :class:`SSHHealth` result."""
        return self._bridge.run(self._client.health())
