"""DHCP collector.

Sources: ``uci show dhcp`` for dnsmasq pool configuration, and
``ubus call dhcp leases`` for current leases.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import DhcpInfo, DhcpLease, DhcpPool

_OPTION_LINE = re.compile(r"^dhcp\.(?P<section>[^=]+)\.(?P<option>\w+)='(?P<value>[^']*)'$")


def _parse_pools(text: str) -> tuple[bool, list[DhcpPool]]:
    sections: dict[str, dict[str, str]] = {}
    for line in text.splitlines():
        m = _OPTION_LINE.match(line.strip())
        if not m:
            continue
        sections.setdefault(m.group("section"), {})[m.group("option")] = m.group("value")

    enabled = True
    pools: list[DhcpPool] = []
    for name, opts in sections.items():
        if name.startswith("@dnsmasq"):
            enabled = opts.get("enable_dnsmasq", "1") != "0"
            continue
        if not name.startswith("@dhcp"):
            continue
        limit = opts.get("limit")
        pools.append(
            DhcpPool(
                name=opts.get("name", name),
                interface=opts.get("interface"),
                start=opts.get("start"),
                limit=int(limit) if limit and limit.isdigit() else None,
                leasetime=opts.get("leasetime"),
            )
        )
    return enabled, pools


def _parse_leases(leases: list[dict]) -> list[DhcpLease]:
    result: list[DhcpLease] = []
    for entry in leases or []:
        if not isinstance(entry, dict) or not entry.get("ip"):
            continue
        result.append(
            DhcpLease(
                hostname=str(entry.get("hostname") or ""),
                ip=str(entry["ip"]),
                mac=entry.get("mac"),
                expires=str(entry["expires"]) if entry.get("expires") else None,
                interface=entry.get("interface"),
            )
        )
    return result


class DhcpCollector(Collector):
    name = "dhcp"

    def collect(self, ctx: CollectorContext) -> DhcpInfo:
        enabled, pools = _parse_pools(ctx.sh("uci show dhcp", default=""))
        leases: list[DhcpLease] = []
        try:
            data = ctx.ubus.call("dhcp", "leases")
            leases = _parse_leases(data.get("leases", []))
        except Exception:  # noqa: BLE001 - leases are optional detail
            pass
        return DhcpInfo(pools=pools, leases=leases, enabled=enabled)
