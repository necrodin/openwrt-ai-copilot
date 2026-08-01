"""ARP table collector.

Source: ``/proc/net/arp``. Normalizes each entry to (ip, mac, interface,
state). ``0x2`` means complete; ``0x0`` means incomplete (no reply yet).
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import ArpEntry


def _parse_arp(text: str) -> list[ArpEntry]:
    entries: list[ArpEntry] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6 or not parts[0].replace(".", "").isdigit():
            continue
        ip, _hwtype, flags, mac, _mask, device = parts[:6]
        state = "complete" if flags == "0x2" else ("incomplete" if flags == "0x0" else flags)
        entries.append(ArpEntry(ip=ip, mac=mac, interface=device, state=state))
    return entries


class ArpCollector(Collector):
    name = "arp"

    def collect(self, ctx: CollectorContext) -> list[ArpEntry]:
        return _parse_arp(ctx.sh("cat /proc/net/arp", default=""))
