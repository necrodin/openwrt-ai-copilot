"""Network interfaces collector.

Sources: ``ubus call network.interface dump`` for interfaces, addresses, proto,
and the WAN/LAN topology; ``ubus call network.device status`` for link state,
speed, MTU, MAC, and byte counters. Device state is merged into the logical
interfaces by device name; kernel/physical devices that no logical interface
references (e.g. wireless interfaces, untagged links) are surfaced as standalone
entries so the UI can render them. Bridges (``br-*``), VLAN tagged interfaces
(``name.N``), the default gateway, and the configured DNS servers are also
surfaced. The network-wide ``gateway`` / ``dns`` / ``wan_interface`` are stored
in ``ctx.state`` so the snapshot assembler can build a :class:`NetworkStatus`.

The parsing is tolerant of the two shapes real OpenWrt firmware emits:

* a top-level object keyed by device name (OpenWrt 23.05+); or
* an object wrapped under a ``device`` key (legacy).

Field names differ too (``macaddr`` vs ``macaddress``, ``carrier`` vs ``link``,
``speed`` as an integer or a string such as ``"1000M"``), all handled here.
"""

from __future__ import annotations

import re
from typing import Any

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import WAN_PROTOS, NetworkAddress, NetworkInterface

_VLAN = re.compile(r"^(.+)\.(\d+)$")


def _address(entry: dict) -> NetworkAddress:
    addr = entry.get("address") or ""
    family = "ipv6" if ":" in addr else "ipv4"
    return NetworkAddress(
        address=addr,
        prefix=int(entry.get("mask") or entry.get("masklen") or 0),
        family=family,
    )


def _vlan_id(name: str) -> int | None:
    match = _VLAN.match(name)
    return int(match.group(2)) if match else None


def _stats_value(stats: dict | None, key: str) -> int | None:
    if stats is None or stats.get(key) is None:
        return None
    try:
        return int(stats[key])
    except (TypeError, ValueError):
        return None


def _int_value(value: Any) -> int | None:
    """Return ``int`` best-effort, tolerating strings and junk."""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _device_map(dev_status: Any) -> dict[str, dict]:
    """Normalize the device-status response into ``{name: info}``.

    Some firmware wraps devices under a ``device`` key; modern OpenWrt returns
    them as a flat object keyed by device name.
    """
    if not isinstance(dev_status, dict):
        return {}
    wrapped = dev_status.get("device")
    if isinstance(wrapped, dict):
        return wrapped
    return {
        name: info
        for name, info in dev_status.items()
        if isinstance(info, dict) and name != "device"
    }


def _interface_addresses(entry: dict) -> list[NetworkAddress]:
    """Collect addresses from both legacy and real OpenWrt response keys."""
    result = [_address(a) for a in entry.get("ipv4-address", [])]
    result += [_address(a) for a in entry.get("ipv6-address", [])]
    if not result:
        result = [_address(a) for a in entry.get("addresses", [])]
    return result


def _is_bridge(device: str | None, dev: dict) -> bool:
    if device and device.startswith("br-"):
        return True
    if not dev:
        return False
    devtype = dev.get("type") or dev.get("devtype")
    return isinstance(devtype, str) and "bridge" in devtype.lower()


def _bridge_members(dev: dict | None) -> list[str]:
    if not dev:
        return []
    if dev.get("type") == "bridge" and isinstance(dev.get("bridge-members"), list):
        return [m for m in dev["bridge-members"] if isinstance(m, str) and m]
    members: list[str] = []
    for port in dev.get("ports", []):
        if isinstance(port, dict):
            name = port.get("ifname") or port.get("name")
            if name:
                members.append(name)
    return members


def _bridge_attribute(dev: dict | None, key: str) -> Any | None:
    if not dev:
        return None
    if isinstance(dev.get("bridge-attributes"), dict):
        return dev["bridge-attributes"].get(key)
    return None


def _speed_mbps(value: Any) -> int | None:
    """Return an integer Mbps value tolerating strings like ``"1000M"``."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return 0 if value <= 0 else value
    digits = re.sub(r"[^0-9]", "", str(value))
    if not digits:
        return None
    try:
        return int(digits)
    except ValueError:
        return None


class NetworkCollector(Collector):
    name = "network"

    def collect(self, ctx: CollectorContext) -> list[NetworkInterface]:
        try:
            dump = ctx.ubus.call("network.interface", "dump")
        except Exception:  # noqa: BLE001
            return self._fallback_ip(ctx)

        devices: dict[str, dict] = {}
        try:
            dev_status = ctx.ubus.call("network.device", "status")
            devices = _device_map(dev_status)
        except Exception:  # noqa: BLE001
            pass

        result: list[NetworkInterface] = []
        referenced = set()
        for entry in dump.get("interface", []):
            name = entry.get("interface") or entry.get("name")
            if not name:
                continue
            referenced.add(name)
            device = entry.get("device") or name
            if device:
                referenced.add(device)
            dev = devices.get(device) if device else None
            stats = dev.get("statistics") if dev else None
            try:
                result.append(
                    NetworkInterface(
                        name=name,
                        up=bool(entry.get("up", False)),
                        proto=entry.get("proto"),
                        device=device,
                        mac=(dev.get("macaddr") or dev.get("macaddress")) if dev else None,
                        link=(
                            dev.get("carrier")
                            if dev is not None and "carrier" in dev
                            else (dev.get("link") if dev else None)
                        ),
                        speed_mbps=_speed_mbps(dev.get("speed")) if dev else None,
                        mtu=_int_value(dev.get("mtu")) if dev else None,
                        rx_bytes=_stats_value(stats, "rx_bytes"),
                        tx_bytes=_stats_value(stats, "tx_bytes"),
                        is_bridge=_is_bridge(device, dev),
                        vlan_id=_vlan_id(device or "") or _vlan_id(name),
                        addresses=_interface_addresses(entry),
                        bridge_members=_bridge_members(dev),
                        stp_enabled=_bridge_attribute(dev, "stp"),
                        forward_delay=_int_value(_bridge_attribute(dev, "forward_delay")),
                        uptime_seconds=_int_value(entry.get("uptime")),
                        rx_errors=_stats_value(stats, "rx_errors"),
                        tx_errors=_stats_value(stats, "tx_errors"),
                        rx_dropped=_stats_value(stats, "rx_dropped"),
                        tx_dropped=_stats_value(stats, "tx_dropped"),
                    )
                )
            except Exception:  # noqa: BLE001 - one bad interface must not sink the section
                continue

        for device, dev in devices.items():
            if device in referenced:
                continue
            stats = dev.get("statistics") if dev else None
            try:
                result.append(
                    NetworkInterface(
                        name=device,
                        up=bool(dev.get("up", False)),
                        proto=None,
                        device=device,
                        mac=(dev.get("macaddr") or dev.get("macaddress")) if dev else None,
                        link=(
                            dev.get("carrier")
                            if "carrier" in dev
                            else (dev.get("link") if dev else None)
                        ),
                        speed_mbps=_speed_mbps(dev.get("speed")) if dev else None,
                        mtu=_int_value(dev.get("mtu")) if dev else None,
                        rx_bytes=_stats_value(stats, "rx_bytes"),
                        tx_bytes=_stats_value(stats, "tx_bytes"),
                        is_bridge=_is_bridge(device, dev),
                        vlan_id=_vlan_id(device or ""),
                        bridge_members=_bridge_members(dev),
                        stp_enabled=_bridge_attribute(dev, "stp"),
                        forward_delay=_int_value(_bridge_attribute(dev, "forward_delay")),
                        rx_errors=_stats_value(stats, "rx_errors"),
                        tx_errors=_stats_value(stats, "tx_errors"),
                        rx_dropped=_stats_value(stats, "rx_dropped"),
                        tx_dropped=_stats_value(stats, "tx_dropped"),
                    )
                )
            except Exception:  # noqa: BLE001 - one bad device must not sink the section
                continue

        gateway, route_device = self._default_route(ctx)
        self._attach_gateway(ctx, result, gateway, route_device)
        self._state_for_snapshot(ctx, result, gateway, route_device)
        return result

    def _fallback_ip(self, ctx: CollectorContext) -> list[NetworkInterface]:
        result: list[NetworkInterface] = []
        for line in ctx.sh("ip -o addr show", default="").splitlines():
            parts = line.split()
            if len(parts) < 4:
                continue
            iface = parts[1].rstrip(":")
            addr = parts[3]
            family = "ipv6" if ":" in addr else "ipv4"
            if not result or result[-1].name != iface:
                result.append(NetworkInterface(name=iface, up=True, addresses=[], proto=None))
            cidr = addr.split("/")[1] if "/" in addr else "0"
            result[-1].addresses.append(
                NetworkAddress(address=addr.split("/")[0], prefix=int(cidr), family=family)
            )
        gateway, route_device = self._default_route(ctx)
        self._attach_gateway(ctx, result, gateway, route_device)
        self._state_for_snapshot(ctx, result, gateway, route_device)
        return result

    @staticmethod
    def _default_route(ctx: CollectorContext) -> tuple[str | None, str | None]:
        """Return ``(gateway_ip, device)`` from the default routing table.

        Prefers the IPv4 default route, then falls back to the IPv6 default
        route for uplink *device* discovery (an IPv6-only WAN has no IPv4
        default). A link-scope default route (``default dev eth0`` with no
        ``via``) has no gateway; only its device is used.
        """
        for table in ("ip -o route show default", "ip -o -6 route show default"):
            for line in ctx.sh(table, default="").splitlines():
                parts = line.split()
                if len(parts) < 2 or parts[0] != "default":
                    continue
                device = None
                if "dev" in parts:
                    device = parts[parts.index("dev") + 1]
                gateway = None
                if "via" in parts:
                    gateway = parts[parts.index("via") + 1]
                elif parts[1] != "dev":
                    return None, device
                if table.startswith("ip -o route show default"):
                    return gateway, device
                if gateway is not None or device is not None:
                    return gateway, device
        try:
            data = ctx.ubus.call("network.route", "dump")
            routes = data.get("route", []) if isinstance(data, dict) else []
            for route in routes:
                if route.get("target") in ("0.0.0.0", "default") and route.get("family") == 4:
                    return route.get("nexthop"), route.get("dev")
        except Exception:  # noqa: BLE001 - route info is best-effort
            pass
        return None, None

    @staticmethod
    def _dns_servers(ctx: CollectorContext) -> list[str]:
        raw = ctx.sh(
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null",
            default="",
        )
        servers: list[str] = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver" and parts[1] not in servers:
                servers.append(parts[1])
        return servers

    def _attach_gateway(
        self,
        ctx: CollectorContext,  # noqa: ARG001 - kept for interface parity
        interfaces: list[NetworkInterface],
        gateway: str | None,
        device: str | None,
    ) -> None:
        if not gateway or not device:
            return
        for iface in interfaces:
            if iface.device == device or iface.name == device:
                iface.gateway = gateway

    def _state_for_snapshot(
        self,
        ctx: CollectorContext,
        interfaces: list[NetworkInterface],
        gateway: str | None,
        device: str | None,
    ) -> None:
        wan_interface = device
        if wan_interface is None:
            wan_name = next(
                (i.name for i in interfaces if i.proto in WAN_PROTOS), None
            )
            wan_interface = wan_name
        ctx.state["network_status"] = {
            "gateway": gateway,
            "dns": self._dns_servers(ctx),
            "wan_interface": wan_interface,
        }
