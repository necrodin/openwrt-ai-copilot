"""SSH backends: asyncssh (preferred), paramiko (fallback), and a mock.

A backend owns exactly one underlying SSH session and knows how to connect, run
a single command, report liveness, and close. Every backend normalizes failures
onto the hierarchy in :mod:`router_agent.transport.ssh.errors`, so callers never
import an SDK.

Selection (:func:`build_backend`):

- ``backend=None`` (auto) uses **asyncssh** when it is importable, otherwise the
  **paramiko** fallback.
- ``backend="asyncssh"`` / ``"paramiko"`` / ``"mock"`` force a backend.
- The **mock** backend is an in-memory fake with scripted outputs and
  simulated failures; it never touches the network and is used by tests and by
  the dashboard's simulated source.
"""

from __future__ import annotations

import asyncio
import time
from contextlib import suppress
from typing import Any, Protocol

from router_agent.errors import CommandError
from router_agent.transport.base import clean_output
from router_agent.transport.ssh.config import SSHConfig, SSHCredentials
from router_agent.transport.ssh.errors import (
    AuthenticationError,
    HostKeyError,
    SSHError,
)
from router_agent.transport.ssh.errors import (
    ConnectionError as SSHConnectionError,
)
from router_agent.transport.ssh.errors import (
    TimeoutError as SSHTimeoutError,
)

__all__ = [
    "SSHBackend",
    "AsyncSSHBackend",
    "ParamikoBackend",
    "MockSSHBackend",
    "build_backend",
    "asyncssh_available",
]


class SSHBackend(Protocol):
    """A single managed SSH session."""

    name: str
    description: str

    async def connect(self) -> None: ...

    async def run(self, command: str, *, timeout: float | None = None) -> str: ...

    async def is_alive(self) -> bool: ...

    async def close(self) -> None: ...


def asyncssh_available() -> bool:
    """True when the preferred ``asyncssh`` package is importable."""
    try:
        import asyncssh  # noqa: F401

        return True
    except ImportError:
        return False


def build_backend(config: SSHConfig, *, name: str | None = None) -> SSHBackend:
    """Return the backend selected by ``name`` (defaults to ``config.backend``).

    ``None``/auto resolves to asyncssh when installed, else the paramiko
    fallback. An explicitly requested backend that is unavailable raises
    :class:`SSHError`.
    """
    name = name or config.backend
    if name == "mock":
        return MockSSHBackend(config)
    if name == "paramiko":
        return ParamikoBackend(config)
    if name == "asyncssh":
        if not asyncssh_available():
            raise SSHError("asyncssh is not installed; install 'openwrt-ai-router-agent[ssh]'")
        return AsyncSSHBackend(config)
    if name is None:
        if asyncssh_available():
            return AsyncSSHBackend(config)
        return ParamikoBackend(config)
    raise SSHError(f"unknown SSH backend: {name!r}")


class AsyncSSHBackend:
    """Backend backed by ``asyncssh`` (preferred when installed)."""

    name = "asyncssh"

    def __init__(self, config: SSHConfig) -> None:
        self._config = config
        self._credentials = config.credentials
        self._conn: Any | None = None

    @property
    def description(self) -> str:
        return f"{self._config.host}:{self._config.port} (asyncssh)"

    @staticmethod
    def _load() -> Any:
        import asyncssh

        return asyncssh

    async def set_keepalive(self, interval: float) -> None:
        if self._conn is not None and interval > 0:
            self._conn.set_keepalive(interval)

    async def connect(self) -> None:
        asyncssh = self._load()
        config = self._config
        creds = self._credentials

        kwargs: dict[str, Any] = {
            "host": config.host,
            "port": config.port,
            "username": creds.username,
            "connect_timeout": config.timeout,
        }
        if creds.password:
            kwargs["password"] = creds.password

        client_keys: list[Any] = []
        if creds.private_key:
            client_keys.append(creds.private_key)
        if creds.private_key_path is not None:
            client_keys.append(
                asyncssh.read_private_key(
                    creds.private_key_path, passphrase=creds.private_key_passphrase
                )
            )
        if client_keys:
            kwargs["client_keys"] = client_keys

        if config.known_hosts is not None:
            kwargs["known_hosts"] = str(config.known_hosts)
        elif config.host_key_policy == "auto":
            # Trust-on-first-use, matching the previous AutoAddPolicy behavior.
            kwargs["host_verification"] = False
        elif config.host_key_policy == "reject":
            kwargs["known_hosts"] = asyncssh.KnownHosts()

        try:
            self._conn = await asyncssh.connect(**kwargs)
        except asyncssh.HostKeyNotVerifiable as exc:
            raise HostKeyError(f"host key verification failed for {config.host}: {exc}") from exc
        except asyncssh.PermissionDenied as exc:
            raise AuthenticationError(
                f"authentication failed for {creds.username}@{config.host}: {exc}"
            ) from exc
        except TimeoutError as exc:
            raise SSHTimeoutError(f"connect to {config.host} timed out") from exc
        except (asyncssh.ConnectError, asyncssh.OSError) as exc:
            raise SSHConnectionError(f"connect to {config.host}: {exc}") from exc

        if config.keepalive_interval > 0:
            self._conn.set_keepalive(config.keepalive_interval)

    async def run(self, command: str, *, timeout: float | None = None) -> str:
        asyncssh = self._load()
        conn = self._conn
        if conn is None or conn.is_closed():
            raise SSHConnectionError(f"not connected to {self.description}")
        timeout = self._config.command_timeout if timeout is None else timeout
        try:
            result = await asyncio.wait_for(conn.run(command, check=False), timeout=timeout)
        except TimeoutError as exc:
            raise SSHTimeoutError(
                f"command timed out after {timeout}s on {self.description}: {command!r}"
            ) from exc
        except (asyncssh.ProcessError, asyncssh.DisconnectError, asyncssh.Error) as exc:
            raise SSHConnectionError(f"command failed on {self.description}: {exc}") from exc
        if result.exit_status != 0:
            raise CommandError(
                f"Command failed ({result.exit_status}) on {self.description}: {command!r}"
                + (f" — {result.stderr.strip()}" if result.stderr.strip() else "")
            )
        return clean_output(result.stdout)

    async def is_alive(self) -> bool:
        return self._conn is not None and not self._conn.is_closed()

    async def close(self) -> None:
        conn, self._conn = self._conn, None
        if conn is not None and not conn.is_closed():
            conn.close()
            with suppress(Exception):  # noqa: BLE001 - closing best effort
                await conn.wait_closed()


class ParamikoBackend:
    """Fallback backend backed by ``paramiko`` (always available)."""

    name = "paramiko"

    def __init__(self, config: SSHConfig) -> None:
        self._config = config
        self._credentials = config.credentials
        self._client: Any | None = None

    @property
    def description(self) -> str:
        return f"{self._config.host}:{self._config.port} (paramiko)"

    @staticmethod
    def _load() -> Any:
        import paramiko

        return paramiko

    async def set_keepalive(self, interval: float) -> None:
        if interval <= 0:
            return
        transport = self._client.get_transport() if self._client is not None else None
        if transport is not None:
            transport.set_keepalive(interval)

    async def connect(self) -> None:
        paramiko = self._load()
        config = self._config
        creds = self._credentials

        client = paramiko.SSHClient()
        if config.known_hosts is not None:
            client.load_host_keys(str(config.known_hosts))
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        elif config.host_key_policy == "system":
            client.load_system_host_keys()
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        elif config.host_key_policy == "reject":
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        connect_kwargs: dict[str, Any] = {
            "hostname": config.host,
            "port": config.port,
            "username": creds.username,
            "password": creds.password or None,
            "key_filename": str(creds.private_key_path) if creds.private_key_path else None,
            "pkey": self._load_pkey(paramiko) if creds.private_key else None,
            "look_for_keys": False,
            "allow_agent": False,
            "timeout": config.timeout,
            "banner_timeout": config.timeout,
        }
        try:
            await asyncio.to_thread(client.connect, **connect_kwargs)
        except paramiko.AuthenticationException as exc:
            raise AuthenticationError(
                f"authentication failed for {creds.username}@{config.host}: {exc}"
            ) from exc
        except paramiko.BadHostKeyException as exc:
            raise HostKeyError(f"host key verification failed for {config.host}: {exc}") from exc
        except (TimeoutError, OSError) as exc:
            raise SSHTimeoutError(f"connect to {config.host} timed out: {exc}") from exc
        except Exception as exc:  # noqa: BLE001 - normalize any SSH failure
            raise SSHConnectionError(f"connect to {config.host}: {exc}") from exc
        self._client = client
        if config.keepalive_interval > 0:
            transport = client.get_transport()
            if transport is not None:
                transport.set_keepalive(config.keepalive_interval)

    @staticmethod
    def _load_pkey(paramiko: Any, creds: SSHCredentials) -> Any | None:
        if not creds.private_key:
            return None
        from io import StringIO

        data = StringIO(creds.private_key)
        passphrase = creds.private_key_passphrase
        for key_class in (
            paramiko.Ed25519Key,
            paramiko.ECDSAKey,
            paramiko.RSAKey,
            paramiko.DSSKey,
        ):
            try:
                return key_class.from_private_key(data, passphrase)
            except Exception:  # noqa: BLE001 - try the next key format
                continue
        return None

    async def run(self, command: str, *, timeout: float | None = None) -> str:
        client = self._client
        if client is None:
            raise SSHConnectionError(f"not connected to {self.description}")
        timeout = self._config.command_timeout if timeout is None else timeout

        def _exec() -> tuple[str, str, int]:
            _stdin, stdout, stderr = client.exec_command(command, timeout=timeout)
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
            return out, err, code

        try:
            out, err, code = await asyncio.to_thread(_exec)
        except TimeoutError as exc:
            raise SSHTimeoutError(
                f"command timed out after {timeout}s on {self.description}: {command!r}"
            ) from exc
        except Exception as exc:  # noqa: BLE001 - normalize remote failures
            raise SSHConnectionError(f"command failed on {self.description}: {exc}") from exc
        if code != 0:
            raise CommandError(
                f"Command failed ({code}) on {self.description}: {command!r}"
                + (f" — {err.strip()}" if err.strip() else "")
            )
        return clean_output(out)

    async def is_alive(self) -> bool:
        client = self._client
        if client is None:
            return False
        transport = client.get_transport()
        return transport is not None and transport.is_active()

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None:
            with suppress(Exception):  # noqa: BLE001 - closing best effort
                await asyncio.to_thread(client.close)


class MockSSHBackend:
    """In-memory backend for tests: scripted outputs + simulated failures.

    Scripts are matched by command prefix. Failures are turned on with the
    ``fail_*`` / ``timeout_*`` constructor flags so tests can exercise every
    branch of the pool, client, and transport without a real SSH server.
    """

    name = "mock"

    def __init__(
        self,
        config: SSHConfig,
        *,
        scripts: dict[str, str] | None = None,
        fail_connect: bool = False,
        fail_auth: bool = False,
        fail_host_key: bool = False,
        timeout_on_connect: bool = False,
        timeout_commands: tuple[str, ...] = (),
        require_username: str | None = None,
        require_password: str | None = None,
        require_key: bool = False,
        drop_after: int = 0,
        latency: float = 0.0,
    ) -> None:
        self._config = config
        self._credentials = config.credentials
        self.scripts = list((scripts or {}).items())
        self.fail_connect = fail_connect
        self.fail_auth = fail_auth
        self.fail_host_key = fail_host_key
        self.timeout_on_connect = timeout_on_connect
        self.timeout_commands = tuple(timeout_commands)
        self.require_username = require_username
        self.require_password = require_password
        self.require_key = require_key
        self.drop_after = drop_after
        self.latency = latency

        self.calls: list[str] = []
        self.keepalive_calls: list[float] = []
        self.connect_count = 0
        self.run_count = 0
        self.connected = False
        self.last_activity: float | None = None

    @property
    def description(self) -> str:
        return f"{self._config.host}:{self._config.port} (mock)"

    async def set_keepalive(self, interval: float) -> None:
        self.keepalive_calls.append(interval)

    async def connect(self) -> None:
        self.connect_count += 1
        if self.fail_connect:
            raise SSHConnectionError(f"mock: connection refused to {self.description}")
        if self.fail_host_key:
            raise HostKeyError(f"mock: host key mismatch for {self._config.host}")
        if self.timeout_on_connect:
            raise SSHTimeoutError(f"mock: connect to {self._config.host} timed out")
        if self.fail_auth:
            raise AuthenticationError(
                f"mock: authentication failed for {self._credentials.username}"
            )
        if (
            self.require_username is not None
            and self.require_username != self._credentials.username
        ):
            raise AuthenticationError("mock: bad username")
        if (
            self.require_password is not None
            and self._credentials.password != self.require_password
        ):
            raise AuthenticationError("mock: bad password")
        if self.require_key and not self._credentials.has_private_key:
            raise AuthenticationError("mock: private key required")
        self.connected = True
        self.run_count = 0
        self.last_activity = time.monotonic()

    async def run(self, command: str, *, timeout: float | None = None) -> str:
        if not self.connected:
            raise SSHConnectionError(f"mock: not connected to {self.description}")
        self.calls.append(command)
        self.run_count += 1
        self.last_activity = time.monotonic()
        if any(command.startswith(prefix) for prefix in self.timeout_commands):
            limit = timeout if timeout is not None else self._config.command_timeout
            raise SSHTimeoutError(f"mock: command timed out after {limit}s: {command!r}")
        if self.latency:
            await asyncio.sleep(self.latency)
        for prefix, output in self.scripts:
            if command.startswith(prefix):
                return output
        raise CommandError(f"mock: no scripted output for {command!r}")

    async def is_alive(self) -> bool:
        if not self.connected:
            return False
        return self.drop_after <= 0 or self.run_count < self.drop_after

    async def close(self) -> None:
        self.connected = False
