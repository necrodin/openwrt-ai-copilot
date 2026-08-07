"""Network interfaces collector.

Sources: ``ubus call network.interface dump`` for interfaces, addresses, proto,
and the WAN/LAN topology; ``ubus call network.device status`` for link state,
speed, MTU, MAC, and byte counters. Devices are merged into their interfaces by
device name. Bridges (``br-*``), VLAN tagged interfaces (``name.N``), the default
gateway, and the configured DNS servers are also surfaced. The network-wide
``gateway`` / ``dns`` / ``wan_interface`` are stored in ``ctx.state`` so the
snapshot assembler can build a :class:`NetworkStatus`.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import NetworkAddress, NetworkInterface

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


class NetworkCollector(Collector):
    name = "network"

    def collect(self, ctx: CollectorContext) -> list[NetworkInterface]:
        try:
            dump = ctx.ubus.call("network.interface", "dump")
        except Exception:  # noqa: BLE001
            return self._fallback_ip(ctx)

        devices = {}
        try:
            dev_status = ctx.ubus.call("network.device", "status")
            devices = dev_status.get("device") if isinstance(dev_status, dict) else {}
        except Exception:  # noqa: BLE001
            pass

        result: list[NetworkInterface] = []
        for entry in dump.get("interface", []):
            name = entry.get("interface") or entry.get("name")
            if not name:
                continue
            device = entry.get("device") or name
            if device is None:
                device = name
            dev = devices.get(device) if device else None
            stats = dev.get("statistics") if dev else None
            result.append(
                NetworkInterface(
                    name=name,
                    up=bool(entry.get("up", False)),
                    proto=entry.get("proto"),
                    device=device,
                    mac=dev.get("macaddress") if dev else None,
                    link=dev.get("link") if dev else None,
                    speed_mbps=int(dev["speed"]) if dev and dev.get("speed") else None,
                    mtu=int(dev["mtu"]) if dev and dev.get("mtu") else None,
                    rx_bytes=int(stats["rx_bytes"]) if stats else None,
                    tx_bytes=int(stats["tx_bytes"]) if stats else None,
                    is_bridge=bool(device and device.startswith("br-")),
                    vlan_id=_vlan_id(device or ""),
                    addresses=[_address(a) for a in entry.get("addresses", [])],
                    bridge_members=(
                        [
                            p.get("ifname") or p.get("name") or ""
                            for p in dev.get("ports", [])
                            if isinstance(p, dict) and (p.get("ifname") or p.get("name"))
                        ]
                        if dev and dev.get("type") == "bridge"
                        else []
                    ),
                    stp_enabled=dev.get("stp") if dev else None,
                    forward_delay=(
                        int(dev["forward_delay"])
                        if dev and dev.get("forward_delay")
                        else None
                    ),
                    uptime_seconds=int(entry["uptime"]) if entry.get("uptime") else None,
                )
            )

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
        """Return ``(gateway_ip, device)`` from the IPv4 routing table."""
        for line in ctx.sh("ip -o route show default", default="").splitlines():
            parts = line.split()
            if len(parts) >= 3 and parts[0] == "default":
                gateway = parts[2]
                device = None
                if "dev" in parts:
                    device = parts[parts.index("dev") + 1]
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
        raw = ctx.sh("cat /etc/resolv.conf /tmp/resolv.conf.d/*.conf 2>/dev/null", default="")
        servers: list[str] = []
        for line in raw.splitlines():
            parts = line.split()
            if len(parts) >= 2 and parts[0] == "nameserver":
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
                (i.name for i in interfaces if i.proto in ("dhcp", "pppoe", "ppp")), None
            )
            wan_interface = wan_name or (interfaces[0].name if interfaces else None)
        ctx.state["network_status"] = {
            "gateway": gateway,
            "dns": self._dns_servers(ctx),
            "wan_interface": wan_interface,
        }
