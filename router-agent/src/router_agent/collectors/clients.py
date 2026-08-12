"""Connected clients collector.

Merges DHCP leases into a single normalized client list. WiFi station data is
reported separately by the wifi collector; clients here are the network-visible
leases handed out by dnsmasq.

Leases come from :func:`router_agent.collectors.dhcp.collect_leases`, which
prefers ``ubus call dhcp leases`` and falls back to the dnsmasq lease file, so
the client list stays populated on firmware where the ubus method is missing.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.collectors.dhcp import collect_leases
from router_agent.model import DhcpLease


class ClientsCollector(Collector):
    name = "clients"

    def collect(self, ctx: CollectorContext) -> list[DhcpLease]:
        return collect_leases(ctx)
