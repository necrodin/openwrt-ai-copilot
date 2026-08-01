"""Common transport contracts."""

from __future__ import annotations

import shlex
from typing import Protocol


class CommandRunner(Protocol):
    """Executes a single shell command and returns its stdout.

    Implementations: :class:`router_agent.transport.ssh.SSHTransport` (remote),
    :class:`router_agent.transport.local.LocalTransport` (on-device), or a test
    fake. Commands are simple, static strings built by collectors — never user
    input — so shell quoting is safe.
    """

    def run(self, command: str, *, timeout: float | None = None) -> str: ...

    def close(self) -> None: ...


def command_tokens(command: str) -> list[str]:
    """Split a static shell command for display/audit purposes."""
    return shlex.split(command)


def clean_output(output: str) -> str:
    """Strip trailing whitespace/CRLF that SSH/ptys sometimes add."""
    return output.replace("\r\n", "\n").strip("\n")
