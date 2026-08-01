"""Connected clients collector.

Merges DHCP leases (``ubus call dhcp leases``) into a single normalized client
list. WiFi station data is reported separately by the wifi collector; clients
here are the network-visible leases handed out by dnsmasq.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import DhcpLease


def _parse_leases(leases: list[dict]) -> list[DhcpLease]:
    result: list[DhcpLease] = []
    for entry in leases or []:
        if not isinstance(entry, dict):
            continue
        ip = entry.get("ip")
        if not ip:
            continue
        result.append(
            DhcpLease(
                hostname=str(entry.get("hostname") or ""),
                ip=str(ip),
                mac=entry.get("mac"),
                expires=str(entry.get("expires")) if entry.get("expires") else None,
                interface=entry.get("interface"),
            )
        )
    return result


class ClientsCollector(Collector):
    name = "clients"

    def collect(self, ctx: CollectorContext) -> list[DhcpLease]:
        try:
            data = ctx.ubus.call("dhcp", "leases")
        except Exception:  # noqa: BLE001
            return []
        return _parse_leases(data.get("leases", []))
