"""DHCP collector.

Sources: ``uci show dhcp`` for the dnsmasq server configuration (pools,
static host leases, gateway/DNS/domain), and the currently active leases.

Active leases come from ``ubus call dhcp leases`` when the firmware exposes it
(some dnsmasq builds lack the ubus ``leases`` method), otherwise they fall back
to the dnsmasq lease file (``/tmp/dhcp.leases`` by default, honoring the
configured ``leasefile`` option). The lease file line format is
``<expiry-epoch> <mac> <ip> <hostname> [<client-id>]``.

Pool ranges are resolved against the live interface IPv4 subnet so UCI's
``start`` (which may be an offset such as ``100`` rather than a full address)
renders as a real address range.
"""

from __future__ import annotations

import ipaddress
import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import DhcpInfo, DhcpLease, DhcpPool, DhcpStaticLease

_OPTION_LINE = re.compile(r"^dhcp\.(?P<section>[^=]+)\.(?P<option>\w+)='(?P<value>[^']*)'$")
_SECTION_LINE = re.compile(r"^dhcp\.(?P<section>[^=.]+)=(?P<type>[^=\s]+)$")

#: Default dnsmasq lease file when ``leasefile`` is not configured in UCI.
DEFAULT_LEASE_FILE = "/tmp/dhcp.leases"


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


def _opt_first(
    opts: dict[str, list[str]],
    key: str,
    default: str | None = None,
) -> str | None:
    return opts.get(key, [default])[0]


def _is_type(name: str, prefix: str, types: dict[str, str], expected: str) -> bool:
    return (name.startswith(f"@{prefix}") or types.get(name) == expected)


def _int_offset(value: str) -> int | None:
    """Return the integer value of a decimal string, or ``None`` when non-numeric."""
    if not value or not value.isdigit():
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _resolve_pool_range(
    start: str | None,
    limit: int | None,
    net: tuple[str, int] | None,
) -> tuple[str | None, str | None]:
    """Resolve a pool's ``(start, range_end)``, handling UCI offset ``start``.

    UCI ``start`` may be a full IPv4 address (``192.168.100.100``) or an offset
    relative to the interface network (``100`` -> ``192.168.100.100`` for a
    ``192.168.100.0/24`` subnet). ``net`` is the pool interface's ``(address,
    prefix)``. When the range cannot be resolved the raw values are returned so
    nothing is fabricated.
    """
    if not start:
        return start, None
    offset = _int_offset(start)
    try:
        if offset is not None:
            if net is None:
                return start, None
            base, prefix = net
            try:
                base_int = int(ipaddress.ip_address(base))
            except ValueError:
                return start, None
            mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
            start_int = (base_int & mask) + offset
        else:
            start_int = int(ipaddress.ip_address(start))
    except (ValueError, OverflowError):
        return start, None
    if not limit or limit <= 0:
        return str(ipaddress.ip_address(start_int)), None
    end_int = start_int + limit - 1
    try:
        end_str = str(ipaddress.ip_address(end_int))
    except (ValueError, OverflowError):
        return str(ipaddress.ip_address(start_int)), None
    return str(ipaddress.ip_address(start_int)), end_str


def _parse_pools(
    sections: dict[str, dict[str, list[str]]],
    types: dict[str, str],
    iface_net: dict[str, tuple[str, int]] | None = None,
) -> tuple[bool, list[DhcpPool]]:
    enabled = True
    pools: list[DhcpPool] = []
    for name, opts in sections.items():
        if _is_type(name, "dnsmasq", types, "dnsmasq"):
            enabled = opts.get("enable_dnsmasq", ["1"])[0] != "0"
            continue
        if not _is_type(name, "dhcp", types, "dhcp"):
            continue

        interface = _opt_first(opts, "interface")
        start = _opt_first(opts, "start")
        limit = _int_offset(_opt_first(opts, "limit") or "")
        net = (iface_net or {}).get(interface or "") if interface else None
        resolved_start, range_end = _resolve_pool_range(start, limit, net)
        pools.append(
            DhcpPool(
                name=_opt_first(opts, "name", name) or name,
                interface=interface,
                start=resolved_start,
                limit=limit,
                leasetime=_opt_first(opts, "leasetime"),
                range_end=range_end,
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
    str | None,
]:
    gateway: str | None = None
    dns: list[str] = []
    domain: str | None = None
    static_leases: list[DhcpStaticLease] = []
    leasefile: str | None = None
    for name, opts in sections.items():
        if _is_type(name, "host", types, "host"):
            static_leases.append(
                DhcpStaticLease(
                    section=name,
                    hostname=_opt_first(opts, "name"),
                    ip=_opt_first(opts, "ip"),
                    mac=_opt_first(opts, "mac"),
                    enabled=opts.get("enabled", ["1"])[0] != "0",
                )
            )
            continue
        # ``dhcp_option`` (gateway=3, DNS=6) is valid on both the dnsmasq
        # section and individual dhcp pool sections (LuCI stores it per pool).
        if not (
            _is_type(name, "dnsmasq", types, "dnsmasq")
            or _is_type(name, "dhcp", types, "dhcp")
        ):
            continue
        if _is_type(name, "dnsmasq", types, "dnsmasq"):
            domain = opts.get("domain", [None])[0]
            leasefile = _opt_first(opts, "leasefile")
        for value in opts.get("dhcp_option", []):
            option_number, _, option_value = value.partition(",")
            option_value = option_value.strip()
            if option_number.strip() == "3" and option_value and gateway is None:
                gateway = option_value
            elif option_number.strip() == "6" and option_value:
                for server in option_value.split(","):
                    server = server.strip()
                    if server and server not in dns:
                        dns.append(server)
    return gateway, dns, domain, static_leases, leasefile


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


def _parse_dnsmasq_lease_file(text: str) -> list[DhcpLease]:
    """Parse dnsmasq lease file lines: ``<expiry> <mac> <ip> <hostname> ...``.

    ``*`` in the hostname field means the client did not send a name. Lease
    expiry is the dnsmasq epoch (seconds); it is preserved so consumers can
    distinguish active from stale/expired leases.
    """
    result: list[DhcpLease] = []
    for line in text.splitlines():
        fields = line.split()
        if len(fields) < 4:
            continue
        expiry, mac, ip, hostname = fields[0], fields[1], fields[2], fields[3]
        if not ip:
            continue
        result.append(
            DhcpLease(
                hostname="" if hostname == "*" else hostname,
                ip=ip,
                mac=mac,
                expires=str(expiry) if _int_offset(expiry) is not None else None,
                interface=None,
            )
        )
    return result


def _expiry_rank(lease: DhcpLease) -> int:
    """Sort/rank key: the numeric expiry, or ``-1`` when unknown."""
    if lease.expires is None:
        return -1
    offset = _int_offset(lease.expires)
    return offset if offset is not None else -1


def _dedupe_leases(leases: list[DhcpLease]) -> list[DhcpLease]:
    """Drop duplicate leases: one entry per device, keeping the newest.

    A device may appear twice when it changes IP or a stale file/ubus entry
    lingers; identity is the MAC (falling back to the IP for MAC-less entries),
    and the lease with the latest expiry wins.
    """
    best: dict[str, DhcpLease] = {}
    order: list[str] = []
    for lease in leases:
        key = (lease.mac or "").lower()
        if not key:
            key = lease.ip
        previous = best.get(key)
        if previous is None or _expiry_rank(lease) >= _expiry_rank(previous):
            if previous is None:
                order.append(key)
            best[key] = lease
    return [best[key] for key in order]


def collect_leases(ctx: CollectorContext, leasefile: str | None = None) -> list[DhcpLease]:
    """Return the currently active DHCP leases.

    Prefers ``ubus call dhcp leases`` when the firmware exposes it, and falls
    back to reading the dnsmasq lease file (``leasefile`` or the OpenWrt
    default). Both sources are best-effort: an unavailable method, a missing
    file, or a file with no leases yields an empty list, never fabricated data.
    """
    try:
        data = ctx.ubus.call("dhcp", "leases")
        leases = _parse_leases(data.get("leases", []))
        if leases:
            return _dedupe_leases(leases)
    except Exception:  # noqa: BLE001 - ubus leases are optional detail
        pass
    raw = ctx.sh(f"cat {leasefile or DEFAULT_LEASE_FILE} 2>/dev/null")
    return _dedupe_leases(_parse_dnsmasq_lease_file(raw))


def _interface_ipv4(dump: dict) -> dict[str, tuple[str, int]]:
    """Map each logical interface to its primary IPv4 ``(address, prefix)``."""
    result: dict[str, tuple[str, int]] = {}
    interfaces = dump.get("interface") if isinstance(dump, dict) else None
    if not isinstance(interfaces, list):
        return result
    for entry in interfaces:
        if not isinstance(entry, dict):
            continue
        name = entry.get("interface") or entry.get("name")
        if not name or name in result:
            continue
        addresses = entry.get("ipv4-address") or []
        for addr in addresses:
            if not isinstance(addr, dict) or not addr.get("address"):
                continue
            mask = addr.get("mask") or addr.get("masklen")
            try:
                result[name] = (str(addr["address"]), int(mask) if mask else 24)
            except (TypeError, ValueError):
                continue
            break
    return result


class DhcpCollector(Collector):
    name = "dhcp"

    def collect(self, ctx: CollectorContext) -> DhcpInfo:
        raw = ctx.sh("uci show dhcp", default="")
        sections, types = _uci_sections(raw)
        iface_net: dict[str, tuple[str, int]] = {}
        try:
            dump = ctx.ubus.call("network.interface", "dump")
            iface_net = _interface_ipv4(dump)
        except Exception:  # noqa: BLE001 - range resolution is best-effort
            pass
        enabled, pools = _parse_pools(sections, types, iface_net)
        gateway, dns, domain, static_leases, leasefile = _parse_dnsmasq(sections, types)
        leases = collect_leases(ctx, leasefile=leasefile)
        return DhcpInfo(
            pools=pools,
            leases=leases,
            static_leases=static_leases,
            enabled=enabled,
            gateway=gateway,
            dns=dns,
            domain=domain,
        )
