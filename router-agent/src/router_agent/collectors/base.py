"""Collector framework.

A collector gathers one section of the normalized snapshot. Collectors only
read device state (ubus / UCI / shell / logread) — never mutate anything.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from router_agent.config import AgentConfig
from router_agent.transport.base import CommandRunner
from router_agent.transport.luci import LuciRpcClient
from router_agent.transport.ubus import UbusClient


@dataclass
class CollectorContext:
    """Everything a collector needs to gather its section."""

    runner: CommandRunner
    ubus: UbusClient
    luci: LuciRpcClient | None = None
    config: AgentConfig = field(default_factory=AgentConfig)
    #: Scratch space shared across collectors (e.g. board info for the meta).
    state: dict[str, Any] = field(default_factory=dict)

    def sh(self, command: str, *, default: str = "") -> str:
        """Run a shell command, returning ``default`` on any failure."""
        try:
            return self.runner.run(command)
        except Exception:  # noqa: BLE001 - best-effort collection
            return default


class Collector(ABC):
    """Base class for a snapshot section collector."""

    name: str = "collector"

    @abstractmethod
    def collect(self, ctx: CollectorContext) -> Any: ...
