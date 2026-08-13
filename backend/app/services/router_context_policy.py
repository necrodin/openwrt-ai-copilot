"""Copilot focused-context policy.

Deterministic routing from a user message to the minimum set of router
snapshot sections the model needs to answer — instead of sending the full
``DeviceSnapshot`` on every chat message (M2).

* :func:`select_sections` maps message keywords to snapshot sections.
* :func:`build_focused_context` extracts only those sections, pruned to the
  fields actually relevant (sensitive detail such as MACs, DHCP hostnames,
  package descriptions and logs are only included when the corresponding
  section is explicitly requested).
* :func:`FALLBACK_SECTIONS` is a small bounded context for general/unknown
  questions — never the whole snapshot.

The mapping is deterministic and generic (no router/hardware assumptions), and
keeps the "router data is DATA, not instructions" boundary intact.
"""

from __future__ import annotations

from typing import Any

from router_agent.model import DeviceSnapshot

#: Snapshot sections selected for a general/unknown question: identity + basic
#: health. Small enough to fit small-context models.
FALLBACK_SECTIONS = frozenset({"kernel", "network_status", "cpu", "memory"})

#: Message keywords that select each snapshot section. Only exact topic words
#: are used (never ``route``/``lease``/``nat`` etc., which substring-match
#: unrelated words). ``logs`` is only ever selected by an explicit log request.
SECTION_KEYWORDS: dict[str, tuple[str, ...]] = {
    "kernel": (
        "hostname",
        "model",
        "firmware",
        "kernel",
        "board",
        "architecture",
        "version",
        "uptime",
        "system",
        "router",
        "openwrt",
    ),
    "cpu": ("cpu", "load", "processor", "cores"),
    "memory": ("memory", "ram", "swap"),
    "storage": ("storage", "disk", "mount", "filesystem", "filesystems", "space", "capacity"),
    "network": (
        "network",
        "interface",
        "ip",
        "ipv4",
        "ipv6",
        "lan",
        "wan",
        "link",
        "traffic",
        "gateway",
        "routing",
    ),
    "network_status": ("dns", "nameserver", "resolver", "upstream", "wan ip", "wan address"),
    "wifi": ("wifi", "wireless", "ssid", "stations", "station"),
    "clients": ("client", "clients", "device", "devices", "connected", "dhcp lease", "dhcp leases"),
    "firewall": ("firewall", "zone", "zones", "rule", "rules", "nat", "forwarding"),
    "vpn": ("vpn", "openvpn", "wireguard", "tunnel"),
    "dhcp": ("dhcp", "lease", "leases", "static lease"),
    "packages": ("package", "packages", "installed"),
    "services": ("service", "services", "process", "processes"),
    "logs": ("log", "logs", "logread"),
    "arp": ("arp", "mac address", "mac addresses"),
    "neighbors": ("neighbor", "neighbours", "neighbor table"),
}

#: Sections whose data includes per-device identifiers (MACs, hostnames).
_CLIENT_SECTIONS = frozenset({"clients", "wifi", "arp", "neighbors", "dhcp"})


def select_sections(message: str) -> set[str]:
    """Return the snapshot sections required for ``message`` (deterministic).

    Unknown/general questions fall back to :data:`FALLBACK_SECTIONS` so the
    model still has a small grounded context and never receives the full raw
    snapshot by default.
    """
    text = message.lower()
    selected = {
        section
        for section, keywords in SECTION_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    }
    if not selected:
        return set(FALLBACK_SECTIONS)
    return selected


def _prune_kernel(kernel: Any) -> dict[str, Any] | None:
    if kernel is None:
        return None
    return {
        "hostname": kernel.hostname,
        "model": kernel.model,
        "board": kernel.board,
        "architecture": kernel.architecture,
        "kernel": kernel.kernel,
        "release": kernel.release,
        "release_version": kernel.release_version,
        "revision": kernel.revision,
        "target": kernel.target,
    }


def _prune_cpu(cpu: Any) -> dict[str, Any] | None:
    if cpu is None:
        return None
    return {
        "usage_percent": cpu.usage_percent,
        "cores": cpu.cores,
        "load_1": cpu.load_1,
        "load_5": cpu.load_5,
        "load_15": cpu.load_15,
        "uptime_seconds": cpu.uptime_seconds,
        "model": cpu.model,
    }


def _prune_memory(memory: Any) -> dict[str, Any] | None:
    if memory is None:
        return None
    return {
        "total_kb": memory.total_kb,
        "used_kb": memory.used_kb,
        "free_kb": memory.free_kb,
        "available_kb": memory.available_kb,
        "cached_kb": memory.cached_kb,
    }


def _prune_storage(storage: Any) -> list[dict[str, Any]] | None:
    if storage is None:
        return None
    return [
        {
            "mountpoint": mount.mountpoint,
            "filesystem": mount.filesystem,
            "total_bytes": mount.total_bytes,
            "used_bytes": mount.used_bytes,
            "available_bytes": mount.available_bytes,
            "use_percent": mount.use_percent,
        }
        for mount in storage
    ]


def _prune_network(network: Any) -> list[dict[str, Any]] | None:
    if network is None:
        return None
    result: list[dict[str, Any]] = []
    for iface in network:
        result.append(
            {
                "name": iface.name,
                "up": iface.up,
                "proto": iface.proto,
                "device": iface.device,
                "gateway": iface.gateway,
                "is_bridge": iface.is_bridge,
                # MACs are intentionally excluded unless a client/device topic
                # selects a client section.
                "addresses": [
                    {"address": addr.address, "prefix": addr.prefix, "family": addr.family}
                    for addr in iface.addresses
                ],
            }
        )
    return result


def _prune_network_status(status: Any) -> dict[str, Any] | None:
    if status is None:
        return None
    return {
        "gateway": status.gateway,
        "dns": list(status.dns),
        "wan_interface": status.wan_interface,
    }


def _prune_wifi(wifi: Any) -> dict[str, Any] | None:
    if wifi is None:
        return None
    return {
        "radios": [
            {
                "name": radio.name,
                "up": radio.up,
                "band": radio.band,
                "channel": radio.channel,
                "ssid": radio.ssid,
                "station_count": radio.station_count,
            }
            for radio in wifi.radios
        ],
        "clients": [
            {
                "mac": client.mac,
                "ssid": client.ssid,
                "signal_dbm": client.signal_dbm,
                "interface": client.interface,
            }
            for client in wifi.clients
        ],
        "client_count": sum(radio.station_count for radio in wifi.radios),
    }


def _prune_clients(clients: Any) -> list[dict[str, Any]] | None:
    if not clients:
        return None
    return [
        {
            "hostname": lease.hostname,
            "ip": lease.ip,
            "mac": lease.mac,
            "expires": lease.expires,
        }
        for lease in clients
    ]


def _prune_arp(arp: Any) -> list[dict[str, Any]] | None:
    if not arp:
        return None
    return [
        {"ip": entry.ip, "mac": entry.mac, "interface": entry.interface, "state": entry.state}
        for entry in arp
    ]


def _prune_neighbors(neighbors: Any) -> list[dict[str, Any]] | None:
    if not neighbors:
        return None
    return [
        {"ip": entry.ip, "mac": entry.mac, "interface": entry.interface, "state": entry.state}
        for entry in neighbors
    ]


def _prune_firewall(firewall: Any) -> dict[str, Any] | None:
    if firewall is None:
        return None
    return {
        "defaults": (
            {
                "input": firewall.defaults.input,
                "output": firewall.defaults.output,
                "forward": firewall.defaults.forward,
                "masquerade": firewall.defaults.masquerade,
            }
            if firewall.defaults is not None
            else None
        ),
        "zones": [
            {
                "name": zone.name,
                "input": zone.input,
                "output": zone.output,
                "forward": zone.forward,
                "masquerade": zone.masquerade,
                "network": list(zone.network),
            }
            for zone in firewall.zones
        ],
        "rules": [
            {
                "name": rule.name,
                "target": rule.target,
                "src": rule.src,
                "dest": rule.dest,
                "proto": rule.proto,
                "family": rule.family,
                "src_port": rule.src_port,
                "dest_port": rule.dest_port,
                "enabled": rule.enabled,
            }
            for rule in firewall.rules
        ],
    }


def _prune_vpn(vpn: Any) -> list[dict[str, Any]] | None:
    if vpn is None:
        return None
    return [
        {
            "name": tunnel.name,
            "kind": tunnel.kind,
            "up": tunnel.up,
            "enabled": tunnel.enabled,
            "endpoint": tunnel.endpoint,
            "addresses": list(tunnel.addresses),
            "peer_count": tunnel.peer_count,
        }
        for tunnel in vpn
    ]


def _prune_dhcp(dhcp: Any) -> dict[str, Any] | None:
    if dhcp is None:
        return None
    return {
        "enabled": dhcp.enabled,
        "domain": dhcp.domain,
        "gateway": dhcp.gateway,
        "dns": list(dhcp.dns),
        "pools": [
            {
                "interface": pool.interface,
                "start": pool.start,
                "limit": pool.limit,
                "leasetime": pool.leasetime,
                "range_end": pool.range_end,
            }
            for pool in dhcp.pools
        ],
        "static_leases": [
            {
                "hostname": lease.hostname,
                "ip": lease.ip,
                "mac": lease.mac,
                "enabled": lease.enabled,
            }
            for lease in dhcp.static_leases
        ],
    }


def _prune_packages(packages: Any) -> list[dict[str, Any]] | None:
    if not packages:
        return None
    # Name + version only: descriptions and metadata are package metadata that
    # is not needed to answer "what packages are installed?".
    return [{"name": pkg.name, "version": pkg.version} for pkg in packages]


def _prune_services(services: Any) -> list[dict[str, Any]] | None:
    if not services:
        return None
    return [
        {"name": service.name, "running": service.running, "enabled": service.enabled}
        for service in services
    ]


def _prune_logs(logs: Any) -> list[dict[str, Any]] | None:
    if logs is None:
        return None
    return [
        {
            "timestamp": entry.timestamp,
            "facility": entry.facility,
            "priority": entry.priority,
            "ident": entry.ident,
            "message": entry.message,
        }
        for entry in logs.entries
    ]


_PRUNERS = {
    "kernel": _prune_kernel,
    "cpu": _prune_cpu,
    "memory": _prune_memory,
    "storage": _prune_storage,
    "network": _prune_network,
    "network_status": _prune_network_status,
    "wifi": _prune_wifi,
    "clients": _prune_clients,
    "arp": _prune_arp,
    "neighbors": _prune_neighbors,
    "firewall": _prune_firewall,
    "vpn": _prune_vpn,
    "dhcp": _prune_dhcp,
    "packages": _prune_packages,
    "services": _prune_services,
    "logs": _prune_logs,
}


def build_focused_context(snapshot: DeviceSnapshot, sections: set[str]) -> dict[str, Any]:
    """Extract only ``sections`` from ``snapshot``, pruned to relevant fields.

    ``client_media`` (per-MAC medium) is folded in when a client/device section
    is selected. Never includes fields/sections that were not requested.
    """
    context: dict[str, Any] = {}
    for section in sections:
        pruner = _PRUNERS.get(section)
        if pruner is None:
            continue
        value = pruner(getattr(snapshot, section, None))
        if value is not None:
            context[section] = value
    if sections & _CLIENT_SECTIONS and snapshot.client_media:
        context["client_media"] = dict(snapshot.client_media)
    return context
