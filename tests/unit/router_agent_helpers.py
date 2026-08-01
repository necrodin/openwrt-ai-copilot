"""Helpers for router agent tests: a scripted command runner."""

from __future__ import annotations

from router_agent.collectors.base import CollectorContext
from router_agent.config import AgentConfig
from router_agent.errors import CommandError
from router_agent.transport.ubus import UbusClient


class FakeRunner:
    """CommandRunner that returns scripted outputs by command prefix."""

    def __init__(self, scripts: dict[str, str] | None = None) -> None:
        self.scripts = list((scripts or {}).items())
        self.calls: list[str] = []

    def run(self, command: str, *, timeout: float | None = None) -> str:
        self.calls.append(command)
        for prefix, output in self.scripts:
            if command.startswith(prefix):
                return output
        raise CommandError(f"no scripted output for {command!r}")

    def close(self) -> None:
        pass


def make_context(scripts: dict[str, str], *, log_lines: int = 200) -> CollectorContext:
    runner = FakeRunner(scripts)
    return CollectorContext(
        runner=runner,
        ubus=UbusClient(runner),
        config=AgentConfig(log_lines=log_lines),
    )
