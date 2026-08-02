"""Synchronous :class:`SSHTransport` facade for the router agent.

The collectors (and the dashboard) consume the synchronous
:class:`~router_agent.transport.base.CommandRunner` contract — ``run() -> str``
and ``close()``. This facade keeps that contract while delegating to the async
:class:`~router_agent.transport.ssh.client.SSHClient` through a background
event-loop bridge. It also exposes ``arun()`` and ``health()`` for async callers.

Backwards compatibility: the previous constructor signature
``SSHTransport(host, *, port, username, password, key_path, connect_timeout,
command_timeout, banner_timeout)`` still works, and a connect failure still
raises a :class:`ConnectionFailedError` (here
:class:`router_agent.transport.ssh.errors.ConnectionError`) at construction time.
"""

from __future__ import annotations

from pathlib import Path

from router_agent.errors import ConnectionFailedError
from router_agent.transport.ssh.backends import SSHBackend
from router_agent.transport.ssh.bridge import EventLoopBridge
from router_agent.transport.ssh.client import SSHClient
from router_agent.transport.ssh.config import SSHConfig, SSHCredentials
from router_agent.transport.ssh.connection import SSHConnection
from router_agent.transport.ssh.health import SSHHealth

__all__ = ["SSHTransport"]


class SSHTransport:
    """Executes commands on a remote OpenWrt device over SSH.

    Uses an internal :class:`SSHClient` (retries, reconnects, keep-alive) and a
    shared pool of connections sized by ``pool_size``.
    """

    def __init__(
        self,
        host: str,
        *,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_path: Path | None = None,
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
        backend: str | SSHBackend | None = None,
        bridge: EventLoopBridge | None = None,
    ) -> None:
        config = SSHConfig(
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
            backend=backend if isinstance(backend, str) else None,
            credentials=SSHCredentials(
                username=username,
                password=password,
                private_key=private_key,
                private_key_path=Path(key_path) if key_path else None,
                private_key_passphrase=private_key_passphrase,
            ),
        )
        if backend is not None and not isinstance(backend, str):
            connection = SSHConnection(config, backend=backend)
            self._client = SSHClient(config, connection=connection)
        else:
            self._client = SSHClient(config)

        self._bridge = bridge if bridge is not None else EventLoopBridge()
        self._owns_bridge = bridge is None
        self._closed = False
        try:
            # Eager connect preserves the previous fail-fast behavior: a device
            # that cannot be reached raises at construction, not on first run.
            self._bridge.run(self._client.connect())
        except ConnectionFailedError:
            self.close()
            raise

    @property
    def host(self) -> str:
        return self._client.config.host

    @property
    def backend(self) -> str:
        return self._client.backend

    # -- synchronous CommandRunner contract --------------------------------- #

    def run(self, command: str, *, timeout: float | None = None) -> str:
        """Run a command and return its cleaned stdout (blocking)."""
        return self._bridge.run(self._client.run(command, timeout=timeout))

    def close(self) -> None:
        """Close the connection and stop the bridge (idempotent)."""
        if self._closed:
            return
        self._closed = True
        try:
            self._bridge.run(self._client.close())
        except Exception:  # noqa: BLE001 - closing best effort
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
