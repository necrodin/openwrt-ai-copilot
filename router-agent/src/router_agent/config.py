"""Router agent configuration.

Connection settings for reaching an OpenWrt device over SSH, plus an optional
LuCI RPC endpoint. No AI or dashboard configuration exists — this agent only
collects data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("/etc/openwrt-ai/agent.toml")


@dataclass
class AgentConfig:
    """How to reach the router and what to collect."""

    device_id: str = "unconfigured"

    host: str = ""
    port: int = 22
    username: str = "root"
    ssh_key_path: Path | None = None
    password: str | None = None
    ssh_timeout: float = 15.0

    # Optional LuCI RPC access (username/password used only for that session).
    luci_url: str | None = None
    luci_username: str | None = None
    luci_password: str | None = None
    luci_path: str = "/ubus"

    command_timeout: float = 20.0
    log_lines: int = 200

    #: Collectors to run; empty means all.
    enabled_collectors: set[str] = field(default_factory=set)
    #: Collectors to skip even if enabled by default.
    disabled_collectors: set[str] = field(default_factory=set)
