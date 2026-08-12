"""Firewall collector.

Reads the UCI firewall configuration (``uci show firewall``) plus runtime state
and normalizes them into :class:`FirewallInfo`: default policies, zones, rules,
port-forwards (redirects), NAT, and current connection-tracking utilization.
This is configuration-state + read-only runtime probing — no firewall changes
are ever made here.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import (
    FirewallConntrack,
    FirewallDefaults,
    FirewallForward,
    FirewallInfo,
    FirewallNat,
    FirewallRule,
    FirewallStatus,
    FirewallZone,
)

_SECTION_LINE = re.compile(r"^firewall\.(?P<key>[^=]+)=(?P<type>\w+)$")
# ``uci show`` prints a list option's values inside one pair of quotes on a
# single line (``option='wan' 'wan6'``); the value is captured greedily and
# split into tokens by :func:`_split_option_value`.
_OPTION_LINE = re.compile(r"^firewall\.(?P<key>[^=]+)\.(?P<option>\w+)='(?P<value>.*)'$")

_TRUE = {"1", "yes", "true", "on"}


def _split_option_value(value: str) -> list[str]:
    """Split a quoted UCI value into tokens.

    ``'lan'`` -> ``["lan"]``; a single-line list ``'wan' 'wan6'`` ->
    ``["wan", "wan6"]``. ``uci show`` emits list values space-separated inside
    one quote pair, which the simple ``[^']*`` capture cannot represent.
    """
    return [token.strip() for token in value.split("' '")]


def _as_bool(value: str | None) -> bool:
    return bool(value and value.lower() in _TRUE)


def _as_int(value: str | None) -> int | None:
    if value is None or not value.isdigit():
        return None
    return int(value)


def _section_enabled(opt: dict) -> bool:
    """UCI enabled semantics: ``enabled '0'``/``disabled '1'`` disables."""
    if "disabled" in opt:
        return not _as_bool(opt["disabled"])
    if "enabled" in opt:
        return opt["enabled"] != "0"
    return True


def parse_uci_firewall(text: str) -> FirewallInfo:
    """Parse ``uci show firewall`` output into a normalized :class:`FirewallInfo`."""
    sections: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        m = _OPTION_LINE.match(line)
        if m:
            key, option, value = m.group("key"), m.group("option"), m.group("value")
            section = sections.setdefault(key, {})
            values = _split_option_value(value)
            existing = section.get(option)
            if existing is None:
                section[option] = values[0] if len(values) == 1 else values
            elif isinstance(existing, list):
                # Repeated option (UCI ``list``) -> accumulate.
                existing.extend(values)
            else:
                section[option] = [existing, *values]
            continue
        m = _SECTION_LINE.match(line)
        if m:
            sections.setdefault(m.group("key"), {"_type": m.group("type")})

    defaults = FirewallDefaults()
    zones: list[FirewallZone] = []
    rules: list[FirewallRule] = []
    forwards: list[FirewallForward] = []
    nat: list[FirewallNat] = []

    for key, section in sections.items():
        stype = section.get("_type")

        if stype == "defaults":
            defaults = FirewallDefaults(
                input=section.get("input"),
                output=section.get("output"),
                forward=section.get("forward"),
                masquerade=_as_bool(section.get("masq")),
                syn_flood=_as_bool(section.get("synflood_protect") or section.get("syn_flood")),
                osf=_as_bool(section.get("osf")),
                mtu=_as_int(section.get("mtu")),
            )
        elif stype == "zone":
            network = section.get("network")
            if isinstance(network, list):
                network_list = list(network)
            elif network:
                network_list = [network]
            else:
                network_list = []
            zones.append(
                FirewallZone(
                    name=section.get("name", ""),
                    enabled=_section_enabled(section),
                    input=section.get("input"),
                    output=section.get("output"),
                    forward=section.get("forward"),
                    masquerade=_as_bool(section.get("masq")),
                    network=network_list,
                    mtu_fix=_as_bool(section.get("mtu_fix")),
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
                    src_port=section.get("src_port"),
                    dest_port=section.get("dest_port"),
                    enabled=_section_enabled(section),
                    section=key,
                )
            )
        elif stype == "redirect":
            forwards.append(
                FirewallForward(
                    name=section.get("name", ""),
                    proto=section.get("proto"),
                    src=section.get("src"),
                    src_dport=section.get("src_dport") or section.get("dport"),
                    src_ip=section.get("src_ip"),
                    dest=section.get("dest"),
                    dest_ip=section.get("dest_ip"),
                    dest_port=section.get("dest_port"),
                    target=section.get("target"),
                    enabled=_section_enabled(section),
                    section=key,
                )
            )
        elif stype == "nat":
            nat.append(
                FirewallNat(
                    name=section.get("name", ""),
                    target=section.get("target"),
                    family=section.get("family"),
                    src=section.get("src"),
                    src_dport=section.get("src_dport"),
                    dest=section.get("dest"),
                    dest_ip=section.get("dest_ip"),
                    dest_port=section.get("dest_port"),
                    proto=section.get("proto"),
                    enabled=_section_enabled(section),
                    section=key,
                )
            )

    return FirewallInfo(
        defaults=defaults,
        zones=zones,
        rules=rules,
        forwards=forwards,
        nat=nat,
    )


def _probe_version(ctx: CollectorContext) -> str | None:
    """Best-effort firewall backend version.

    ``fw3 -v`` prints a version; ``fw4 -v`` treats ``-v`` as a *verbose* flag
    and prints its usage text (exit 0) instead of a version. Usage/help output
    is therefore rejected and reported as unavailable (``None``) rather than
    surfaced as a bogus version string.
    """
    raw = ctx.sh("fw4 -v 2>/dev/null || fw3 -v 2>/dev/null", default="").strip()
    if not raw:
        return None
    first = raw.splitlines()[0].strip()
    if not first or first.lower().startswith("usage"):
        return None
    return first


def _parse_status(ctx: CollectorContext) -> FirewallStatus:
    running = bool(
        ctx.sh(
            "([ -f /var/run/fw4.state ] || [ -f /tmp/fw4.state ] "
            "|| pgrep -x fw4 >/dev/null 2>&1) && echo 1",
            default="",
        ).strip()
    )
    enabled = bool(ctx.sh("ls /etc/rc.d/S*firewall 2>/dev/null", default="").strip())
    return FirewallStatus(
        running=running,
        enabled=enabled,
        version=_probe_version(ctx),
    )


def _parse_conntrack(ctx: CollectorContext) -> FirewallConntrack | None:
    count = _as_int(
        ctx.sh("cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null", default="").strip()
    )
    maximum = _as_int(
        ctx.sh("cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null", default="").strip()
    )
    if count is None and maximum is None:
        return None
    return FirewallConntrack(count=count, max=maximum)


class FirewallCollector(Collector):
    name = "firewall"

    def collect(self, ctx: CollectorContext) -> FirewallInfo:
        config = parse_uci_firewall(ctx.sh("uci show firewall", default=""))
        config.status = _parse_status(ctx)
        config.conntrack = _parse_conntrack(ctx)
        return config
