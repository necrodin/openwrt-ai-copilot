"""Network interfaces collector.

Sources: ``ubus call network.interface dump`` for interfaces, addresses, and
proto; ``ubus call network.device status`` for link state, speed, MAC, and byte
counters. Devices are merged into their interfaces by device name.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import NetworkAddress, NetworkInterface


def _address(entry: dict) -> NetworkAddress:
    addr = entry.get("address") or ""
    family = "ipv6" if ":" in addr else "ipv4"
    return NetworkAddress(
        address=addr,
        prefix=int(entry.get("mask") or entry.get("masklen") or 0),
        family=family,
    )


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
            device = entry.get("device")
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
                    rx_bytes=int(stats["rx_bytes"]) if stats else None,
                    tx_bytes=int(stats["tx_bytes"]) if stats else None,
                    addresses=[_address(a) for a in entry.get("addresses", [])],
                )
            )
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
        return result
