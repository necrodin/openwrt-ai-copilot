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


def _uci_sections(text: str) -> dict[str, dict[str, list[str]]]:
    sections: dict[str, dict[str, list[str]]] = {}
    for line in text.splitlines():
        m = _OPTION_LINE.match(line.strip())
        if not m:
            continue
        section, option, value = m.group("section"), m.group("option"), m.group("value")
        sections.setdefault(section, {}).setdefault(option, []).append(value)
    return sections


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


def _parse_pools(sections: dict[str, dict[str, list[str]]]) -> tuple[bool, list[DhcpPool]]:
    enabled = True
    pools: list[DhcpPool] = []
    for name, opts in sections.items():
        if name.startswith("@dnsmasq"):
            enabled = opts.get("enable_dnsmasq", ["1"])[0] != "0"
            continue
        if not name.startswith("@dhcp"):
            continue
        first = lambda key, default=None: opts.get(key, [default])[0]
        start = first("start")
        limit = first("limit")
        pools.append(
            DhcpPool(
                name=first("name", name) or name,
                interface=first("interface"),
                start=start,
                limit=int(limit) if limit and limit.isdigit() else None,
                leasetime=first("leasetime"),
                range_end=_range_end(start, limit),
            )
        )
    return enabled, pools


def _parse_dnsmasq(sections: dict[str, dict[str, list[str]]]) -> tuple[
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
        if name.startswith("@dnsmasq"):
            domain = opts.get("domain", [None])[0]
            for value in opts.get("dhcp_option", []):
                option_number, _, option_value = value.partition(",")
                option_value = option_value.strip()
                if option_number.strip() == "3" and option_value:
                    gateway = option_value
                elif option_number.strip() == "6" and option_value:
                    dns.extend(s for s in option_value.split(",") if s.strip())
        elif name.startswith("@host"):
            first = lambda key, default=None: opts.get(key, [default])[0]
            static_leases.append(
                DhcpStaticLease(
                    section=name,
                    hostname=first("name"),
                    ip=first("ip"),
                    mac=first("mac"),
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
        sections = _uci_sections(raw)
        enabled, pools = _parse_pools(sections)
        gateway, dns, domain, static_leases = _parse_dnsmasq(sections)
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