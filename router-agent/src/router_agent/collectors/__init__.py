"""Collector registry.

All built-in collectors, keyed by their normalized section name. The agent only
collects data — there is deliberately no AI, mutation, or dashboard code here.
"""

from __future__ import annotations

from router_agent.collectors.arp import ArpCollector
from router_agent.collectors.base import Collector, CollectorContext
from router_agent.collectors.clients import ClientsCollector
from router_agent.collectors.cpu import CpuCollector
from router_agent.collectors.dhcp import DhcpCollector
from router_agent.collectors.firewall import FirewallCollector
from router_agent.collectors.kernel import KernelCollector
from router_agent.collectors.logs import LogsCollector
from router_agent.collectors.memory import MemoryCollector
from router_agent.collectors.network import NetworkCollector
from router_agent.collectors.packages import PackagesCollector
from router_agent.collectors.routing import RoutingCollector
from router_agent.collectors.storage import StorageCollector
from router_agent.collectors.temperature import TemperatureCollector
from router_agent.collectors.vpn import VpnCollector
from router_agent.collectors.wifi import WifiCollector

ALL_COLLECTORS: dict[str, type[Collector]] = {
    cls.name: cls
    for cls in (
        CpuCollector,
        MemoryCollector,
        TemperatureCollector,
        StorageCollector,
        NetworkCollector,
        FirewallCollector,
        WifiCollector,
        ClientsCollector,
        ArpCollector,
        RoutingCollector,
        VpnCollector,
        DhcpCollector,
        PackagesCollector,
        KernelCollector,
        LogsCollector,
    )
}

COLLECTOR_NAMES = tuple(ALL_COLLECTORS)


def select_collectors(
    config: object,
) -> list[Collector]:
    """Instantiate the enabled collectors (respecting config exclusions)."""
    from router_agent.config import AgentConfig

    if not isinstance(config, AgentConfig):
        raise TypeError("select_collectors requires an AgentConfig")
    names = COLLECTOR_NAMES
    if config.enabled_collectors:
        names = tuple(n for n in names if n in config.enabled_collectors)
    names = tuple(n for n in names if n not in config.disabled_collectors)
    return [ALL_COLLECTORS[name]() for name in names]


__all__ = [
    "ALL_COLLECTORS",
    "COLLECTOR_NAMES",
    "Collector",
    "CollectorContext",
    "select_collectors",
]
