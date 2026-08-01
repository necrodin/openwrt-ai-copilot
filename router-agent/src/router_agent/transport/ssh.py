"""SSH transport to an OpenWrt device (paramiko).

Collectors emit static, allowlisted commands; SSHTransport executes them over a
single persistent SSH session and returns stdout. The session is closed with
:meth:`close`.
"""

from __future__ import annotations

from contextlib import suppress
from pathlib import Path

import paramiko

from router_agent.errors import CommandError, ConnectionFailedError
from router_agent.transport.base import clean_output


class SSHTransport:
    """Executes commands on a remote OpenWrt device over SSH."""

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
        banner_timeout: float = 15.0,
    ) -> None:
        self._host = host
        self._client = paramiko.SSHClient()
        self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self._command_timeout = command_timeout
        try:
            self._client.connect(
                hostname=host,
                port=port,
                username=username,
                password=password or None,
                key_filename=str(key_path) if key_path else None,
                look_for_keys=False,
                allow_agent=False,
                timeout=connect_timeout,
                banner_timeout=banner_timeout,
            )
        except Exception as exc:  # noqa: BLE001 - wrap any SSH failure uniformly
            raise ConnectionFailedError(f"SSH connect to {host}: {exc}") from exc

    def run(self, command: str, *, timeout: float | None = None) -> str:
        try:
            _stdin, stdout, stderr = self._client.exec_command(
                command, timeout=timeout or self._command_timeout
            )
            out = stdout.read().decode("utf-8", "replace")
            err = stderr.read().decode("utf-8", "replace")
            code = stdout.channel.recv_exit_status()
        except Exception as exc:  # noqa: BLE001 - normalize remote failures
            raise CommandError(f"SSH command failed on {self._host}: {exc}") from exc
        if code != 0:
            raise CommandError(
                f"Command failed ({code}) on {self._host}: {command!r}"
                + (f" — {err.strip()}" if err.strip() else "")
            )
        return clean_output(out)

    def close(self) -> None:
        with suppress(Exception):  # noqa: BLE001 - closing best effort
            self._client.close()
