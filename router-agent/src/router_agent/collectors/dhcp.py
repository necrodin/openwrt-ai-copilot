"""DHCP collector.

Sources: ``uci show dhcp`` for the dnsmasq server configuration (pools,
static host leases, gateway/DNS/domain), and ``ubus call dhcp leases`` for the
currently active leases.
"""

from __future__ import annotations

import ipaddress
import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import DhcpInfo, DhcpLease, DhcpPool, DhcpStaticLease

_OPTION_LINE = re.compile(r"^dhcp\.(?P<section>[^=]+)\.(?P<option>\w+)='(?P<value>[^']*)'$")
_SECTION_LINE = re.compile(r"^dhcp\.(?P<section>[^=.]+)=(?P<type>[^=\s]+)$")


def _uci_sections(
    text: str,
) -> tuple[dict[str, dict[str, list[str]]], dict[str, str]]:
    """Parse ``uci show dhcp`` into ``(sections, types)``.

    Sections may be anonymous (``@dhcp[0]``) or named (``config dhcp 'lan'``
    shows up as ``dhcp.lan=dhcp``); ``types`` records the UCI section type so
    named sections are matched the same way anonymous ones are.
    """
    sections: dict[str, dict[str, list[str]]] = {}
    types: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        section_line = _SECTION_LINE.match(line)
        if section_line:
            types[section_line.group("section")] = section_line.group("type")
            continue
        m = _OPTION_LINE.match(line)
        if not m:
            continue
        section, option, value = m.group("section"), m.group("option"), m.group("value")
        sections.setdefault(section, {}).setdefault(option, []).append(value)
    return sections, types


def _range_end(start: str | None, limit: str | None) -> str | None:
    if not start or not limit or not limit.isdigit():
        return None
    try:
        address = ipaddress.ip_address(start)
        if address.version != 4:
            return None
        return str(address + (int(limit) - 1))
    except (ValueError, OverflowError):
        return None


def _opt_first(
    opts: dict[str, list[str]],
    key: str,
    default: str | None = None,
) -> str | None:
    return opts.get(key, [default])[0]


def _is_type(name: str, prefix: str, types: dict[str, str], expected: str) -> bool:
    return (name.startswith(f"@{prefix}") or types.get(name) == expected)


def _parse_pools(
    sections: dict[str, dict[str, list[str]]],
    types: dict[str, str],
) -> tuple[bool, list[DhcpPool]]:
    enabled = True
    pools: list[DhcpPool] = []
    for name, opts in sections.items():
        if _is_type(name, "dnsmasq", types, "dnsmasq"):
            enabled = opts.get("enable_dnsmasq", ["1"])[0] != "0"
            continue
        if not _is_type(name, "dhcp", types, "dhcp"):
            continue

        start = _opt_first(opts, "start")
        limit = _opt_first(opts, "limit")
        pools.append(
            DhcpPool(
                name=_opt_first(opts, "name", name) or name,
                interface=_opt_first(opts, "interface"),
                start=start,
                limit=int(limit) if limit and limit.isdigit() else None,
                leasetime=_opt_first(opts, "leasetime"),
                range_end=_range_end(start, limit),
            )
        )
    return enabled, pools


def _parse_dnsmasq(
    sections: dict[str, dict[str, list[str]]],
    types: dict[str, str],
) -> tuple[
    str | None,
    list[str],
    str | None,
    list[DhcpStaticLease],
]:
    gateway: str | None = None
    dns: list[str] = []
    domain: str | None = None
    static_leases: list[DhcpStaticLease] = []
    for name, opts in sections.items():
        if _is_type(name, "dnsmasq", types, "dnsmasq"):
            domain = opts.get("domain", [None])[0]
            for value in opts.get("dhcp_option", []):
                option_number, _, option_value = value.partition(",")
                option_value = option_value.strip()
                if option_number.strip() == "3" and option_value:
                    gateway = option_value
                elif option_number.strip() == "6" and option_value:
                    dns.extend(s for s in option_value.split(",") if s.strip())
        elif _is_type(name, "host", types, "host"):
            static_leases.append(
                DhcpStaticLease(
                    section=name,
                    hostname=_opt_first(opts, "name"),
                    ip=_opt_first(opts, "ip"),
                    mac=_opt_first(opts, "mac"),
                    enabled=opts.get("enabled", ["1"])[0] != "0",
                )
            )
    return gateway, dns, domain, static_leases


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
        raw = ctx.sh("uci show dhcp", default="")
        sections, types = _uci_sections(raw)
        enabled, pools = _parse_pools(sections, types)
        gateway, dns, domain, static_leases = _parse_dnsmasq(sections, types)
        leases: list[DhcpLease] = []
        try:
            data = ctx.ubus.call("dhcp", "leases")
            leases = _parse_leases(data.get("leases", []))
        except Exception:  # noqa: BLE001 - leases are optional detail
            pass
        return DhcpInfo(
            pools=pools,
            leases=leases,
            static_leases=static_leases,
            enabled=enabled,
            gateway=gateway,
            dns=dns,
            domain=domain,
        )