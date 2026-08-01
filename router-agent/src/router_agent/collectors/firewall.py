"""Firewall collector.

Reads the UCI firewall configuration (``uci show firewall``) and normalizes
zones and rules. This is configuration-state collection — no firewall changes
are ever made.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import FirewallInfo, FirewallRule, FirewallZone

_SECTION_LINE = re.compile(r"^firewall\.(?P<key>[^=]+)=(?P<type>\w+)$")
_OPTION_LINE = re.compile(r"^firewall\.(?P<key>[^=]+)\.(?P<option>\w+)='(?P<value>[^']*)'$")


def parse_uci_firewall(text: str) -> tuple[list[FirewallZone], list[FirewallRule]]:
    sections: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        m = _OPTION_LINE.match(line)
        if m:
            section = sections.setdefault(m.group("key"), {})
            section[m.group("option")] = m.group("value")
            continue
        m = _SECTION_LINE.match(line)
        if m:
            sections.setdefault(m.group("key"), {"type": m.group("type")})

    zones: list[FirewallZone] = []
    rules: list[FirewallRule] = []
    for section in sections.values():
        stype = section.get("type")
        if stype == "zone":
            zones.append(
                FirewallZone(
                    name=section.get("name", ""),
                    input=section.get("input"),
                    output=section.get("output"),
                    forward=section.get("forward"),
                    masquerade=section.get("masq") == "1",
                )
            )
        elif stype == "rule":
            rules.append(
                FirewallRule(
                    name=section.get("name", ""),
                    src=section.get("src"),
                    dest=section.get("dest"),
                    proto=section.get("proto"),
                    target=section.get("target"),
                    family=section.get("family"),
                    dest_port=section.get("dest_port"),
                )
            )
    return zones, rules


class FirewallCollector(Collector):
    name = "firewall"

    def collect(self, ctx: CollectorContext) -> FirewallInfo:
        zones, rules = parse_uci_firewall(ctx.sh("uci show firewall", default=""))
        return FirewallInfo(zones=zones, rules=rules)
