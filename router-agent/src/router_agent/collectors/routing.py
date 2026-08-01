"""Routing table collector.

Sources: ``ip -o route show`` and ``ip -o -6 route show``. Normalizes each
route to (destination, gateway, interface, metric, family).
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import RouteEntry


def _parse_routes(text: str, family: str) -> list[RouteEntry]:
    entries: list[RouteEntry] = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        destination = parts[0]
        i = 1
        gateway = None
        interface = None
        metric = None
        flags = ""
        if parts[1] == "via" and len(parts) >= 3:
            gateway = parts[2]
            i = 3
        while i < len(parts):
            if parts[i] == "dev" and i + 1 < len(parts):
                interface = parts[i + 1]
                i += 2
            elif parts[i] == "metric" and i + 1 < len(parts):
                with suppress(ValueError):
                    metric = int(parts[i + 1])
                i += 2
            elif parts[i] == "proto" and i + 1 < len(parts):
                i += 2
            else:
                i += 1
        entries.append(
            RouteEntry(
                destination=destination,
                gateway=gateway,
                interface=interface,
                metric=metric,
                family=family,
                flags=flags,
            )
        )
    return entries


class RoutingCollector(Collector):
    name = "routing"

    def collect(self, ctx: CollectorContext) -> list[RouteEntry]:
        v4 = _parse_routes(ctx.sh("ip -o route show", default=""), "ipv4")
        v6 = _parse_routes(ctx.sh("ip -o -6 route show", default=""), "ipv6")
        return v4 + v6
