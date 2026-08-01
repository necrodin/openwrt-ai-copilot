"""VPN tunnel collector.

Sources: ``wg show all interfaces`` for WireGuard runtime state,
``ubus call network.interface dump`` to detect tunnel interfaces, and
``uci show openvpn`` for OpenVPN config. Only reads — never starts or stops
tunnels.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import VpnTunnel

_WG_LINE = re.compile(r"^(?P<iface>\S+):\s+(?P<key>\S+):\s+(?P<value>.+)$")


def _parse_wg(text: str) -> dict[str, dict]:
    tunnels: dict[str, dict] = {}
    current: dict | None = None
    for line in text.splitlines():
        m = _WG_LINE.match(line.strip())
        if not m:
            continue
        iface = m.group("iface")
        key = m.group("key")
        value = m.group("value")
        if key == "public-key":
            current = tunnels.setdefault(iface, {"name": iface})
            current["public_key"] = value
        elif current is not None:
            if key == "listen-port":
                current["listen_port"] = int(value)
            elif key == "peer":
                current.setdefault("peers", []).append(
                    {"public_key": value, "endpoint": None, "allowed_ips": []}
                )
            elif key == "endpoint" and current.get("peers"):
                current["peers"][-1]["endpoint"] = value
            elif key == "allowed-ips" and current.get("peers"):
                current["peers"][-1]["allowed_ips"] = value.split(", ")
    return tunnels


class VpnCollector(Collector):
    name = "vpn"

    def collect(self, ctx: CollectorContext) -> list[VpnTunnel]:
        tunnels: list[VpnTunnel] = []

        wg = _parse_wg(ctx.sh("wg show all interfaces", default=""))
        seen: set[str] = set()

        network_ifaces: list[dict] = []
        try:
            dump = ctx.ubus.call("network.interface", "dump")
            network_ifaces = dump.get("interface", [])
        except Exception:  # noqa: BLE001
            pass

        for entry in network_ifaces:
            proto = entry.get("proto")
            name = entry.get("interface")
            if not name:
                continue
            if proto in ("wireguard", "openvpn"):
                seen.add(name)
                tunnels.append(self._tunnel_from_network(entry, wg.get(name, {})))

        # Tunnels visible at runtime via `wg show` but not (yet) matched to a
        # network interface entry are still reported.
        for name, runtime in wg.items():
            if name in seen:
                continue
            tunnels.append(
                VpnTunnel(
                    name=name,
                    kind="wireguard",
                    up=False,
                    public_key=runtime.get("public_key"),
                    listen_port=runtime.get("listen_port"),
                    peer_count=len(runtime.get("peers", [])),
                    detail={
                        "peers": [
                            {
                                "public_key": p["public_key"],
                                "endpoint": p.get("endpoint"),
                                "allowed_ips": p.get("allowed_ips", []),
                            }
                            for p in runtime.get("peers", [])
                        ]
                    },
                )
            )

        self._collect_openvpn_config(ctx, tunnels)
        return tunnels

    @staticmethod
    def _tunnel_from_network(entry: dict, runtime: dict) -> VpnTunnel:
        peers = runtime.get("peers", [])
        addresses = [
            (a.get("address") or "") for a in entry.get("addresses", []) if a.get("address")
        ]
        return VpnTunnel(
            name=entry["interface"],
            kind=entry.get("proto") or "other",
            up=bool(entry.get("up", False)),
            public_key=runtime.get("public_key"),
            listen_port=runtime.get("listen_port"),
            addresses=addresses,
            peer_count=len(peers),
            detail={
                "peers": [
                    {
                        "public_key": p["public_key"],
                        "endpoint": p.get("endpoint"),
                        "allowed_ips": p.get("allowed_ips", []),
                    }
                    for p in peers
                ]
            },
        )

    def _collect_openvpn_config(self, ctx: CollectorContext, tunnels: list[VpnTunnel]) -> None:
        sections: dict[str, dict[str, str]] = {}
        for line in ctx.sh("uci show openvpn", default="").splitlines():
            line = line.strip()
            if line.startswith("openvpn.") and "=" in line:
                key, _, value = line.partition("=")
                rest = key[len("openvpn.") :]
                if not rest:
                    continue
                if "." in rest:
                    section, option = rest.split(".", 1)
                else:
                    section, option = rest, ""
                if option:
                    sections.setdefault(section, {})[option] = value.strip("'")
        for name, opts in sections.items():
            tunnels.append(
                VpnTunnel(
                    name=name,
                    kind="openvpn",
                    up=opts.get("enabled") == "1",
                    endpoint=f"{opts.get('remote')}:{opts.get('port')}"
                    if opts.get("remote")
                    else None,
                    detail={"role": "server" if opts.get("mode") == "server" else "client"},
                )
            )
