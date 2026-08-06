"""IPv6 neighbor (ND cache) collector.

Source: ``ip -6 neigh show``. Maps each on-link IPv6 address to the device's
link-layer (MAC) address and reachability state. This is the IPv6 counterpart
of the ARP (IPv4) collector and lets clients be resolved across both address
families. Entries without a resolved MAC are kept but are not mergeable into a
client (they carry no link-layer identity).
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import NeighborEntry

_REACHABLE_STATES = {"reachable", "stale", "delay", "probe", "permanent", "noarp"}


def _parse_neighbors(text: str) -> list[NeighborEntry]:
    entries: list[NeighborEntry] = []
    for line in text.splitlines():
        parts = line.split()
        if not parts:
            continue
        ip = parts[0]
        if ":" not in ip:
            continue
        mac: str | None = None
        iface: str | None = None
        flags: list[str] = []
        idx = 1
        while idx < len(parts):
            token = parts[idx]
            if token == "dev" and idx + 1 < len(parts):
                iface = parts[idx + 1]
                idx += 2
            elif token == "lladdr" and idx + 1 < len(parts):
                mac = parts[idx + 1]
                idx += 2
            else:
                flags.append(token)
                idx += 1
        lower = [flag.lower() for flag in flags]
        state = next((flag for flag in lower if flag in _REACHABLE_STATES), None)
        entries.append(NeighborEntry(ip=ip, mac=mac, interface=iface, state=state, family="ipv6"))
    return entries


class NeighborsCollector(Collector):
    name = "neighbors"

    def collect(self, ctx: CollectorContext) -> list[NeighborEntry]:
        text = ctx.sh("ip -6 neigh show", default="")
        return _parse_neighbors(text)
