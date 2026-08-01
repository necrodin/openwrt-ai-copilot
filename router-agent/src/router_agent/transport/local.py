"""Local command execution (runs directly on the device).

Used when the agent is installed on the OpenWrt router itself, and as a test
double for SSH. Commands are static strings built by collectors.
"""

from __future__ import annotations

import subprocess

from router_agent.errors import CommandError
from router_agent.transport.base import clean_output


class LocalTransport:
    """Runs commands through ``subprocess``."""

    def __init__(self) -> None:
        self._closed = False

    def run(self, command: str, *, timeout: float | None = None) -> str:
        if self._closed:
            raise CommandError("LocalTransport is closed")
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise CommandError(f"Command timed out: {command!r}") from exc
        if result.returncode != 0:
            stderr = (result.stderr or "").strip()
            raise CommandError(
                f"Command failed ({result.returncode}): {command!r}"
                + (f" — {stderr}" if stderr else "")
            )
        return clean_output(result.stdout)

    def close(self) -> None:
        self._closed = True
