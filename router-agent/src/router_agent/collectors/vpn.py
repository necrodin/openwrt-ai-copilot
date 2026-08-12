"""VPN tunnel and service collector.

Reads real, on-device VPN state:

- WireGuard via ``wg`` (interfaces, peer endpoints/allowed-IPs, handshake times,
  transfer counters, persistent keepalive) merged with ``netifd`` interface
  addresses.
- OpenVPN via ``uci show openvpn`` (per-instance config) plus ``netifd`` link
  state.
- Tailscale / IPsec / Zerotier only when their tools are installed; otherwise
  they are not reported at all so the UI can hide those sections.

Never starts or stops tunnels — collection is read-only.
"""

from __future__ import annotations

import json
import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import VpnTunnel

#: strongSwan ``ipsec statusall`` summary line: ``Security Associations (N up, M
#: connecting)``.
_IPSEC_SUMMARY = re.compile(r"Security Associations \((\d+) up")


#: Keys ``wg show all interfaces`` emits; any other ``iface: key: value`` line
#: (e.g. a shell error like ``ash: wg: not found`` when stderr is captured into
#: stdout) is ignored so an error can never be mistaken for a tunnel.
_WG_KEYS = {"public-key", "listen-port", "peer", "endpoint", "allowed-ips"}


def _parse_wg_interfaces(text: str) -> dict[str, dict]:
    """Parse ``wg show all interfaces`` into {iface: {pubkey, port, peers[]}}.

    Input lines are ``<iface>:\\t<entry>: <value>`` (as produced by the OpenWrt
    ``wg`` wrapper). Sample::

        wg0:\\tpublic-key: XXXX
        wg0:\\tlisten-port: 51820
        wg0:\\tpeer: YYYY
        wg0:\\tendpoint: 198.51.100.7:51820
        wg0:\\tallowed-ips: 10.0.0.2/32, fd0::2/128
    """
    tunnels: dict[str, dict] = {}
    for raw in text.splitlines():
        head, sep, rest = raw.partition(":")
        if not sep:
            continue
        iface = head.strip()
        record = rest.strip()
        key, _, value = record.partition(":")
        key = key.strip()
        if key not in _WG_KEYS:
            continue
        value = value.strip()
        current = tunnels.setdefault(iface, {"name": iface, "peers": []})
        if key == "public-key":
            current["public_key"] = value
        elif key == "listen-port":
            current["listen_port"] = _to_int(value)
        elif key == "peer":
            current.setdefault("peers", []).append(
                {"public_key": value, "endpoint": None, "allowed_ips": []}
            )
        elif key == "endpoint" and current.get("peers"):
            current["peers"][-1]["endpoint"] = value
        elif key == "allowed-ips" and current.get("peers"):
            current["peers"][-1]["allowed_ips"] = value.split(", ")
    return tunnels


def _parse_wg_peer_map(text: str) -> dict[tuple[str, str], list[str]]:
    """Parse tabular ``wg show all ...`` output keyed by (iface, peer)."""
    mapping: dict[tuple[str, str], list[str]] = {}
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        iface = parts[0].strip()
        peer = parts[1].strip()
        if iface and peer:
            mapping[(iface, peer)] = parts[2:]
    return mapping


def _to_int(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _enrich_wg_peers(
    tunnels: dict[str, dict],
    *,
    handshakes: dict[tuple[str, str], list[str]],
    transfer: dict[tuple[str, str], list[str]],
    keepalive: dict[tuple[str, str], list[str]],
) -> None:
    for iface, data in tunnels.items():
        total_rx = 0
        total_tx = 0
        latest = None
        for peer in data.get("peers", []):
            pkey = peer["public_key"]
            hs = handshakes.get((iface, pkey))
            tr = transfer.get((iface, pkey))
            ka = keepalive.get((iface, pkey))
            handshake = _to_int(hs[0]) if hs else None
            peer["latest_handshake"] = handshake
            peer["persistent_keepalive"] = _to_int(ka[0]) if ka else None
            if tr:
                peer["rx_bytes"] = _to_int(tr[0])
                peer["tx_bytes"] = _to_int(tr[1])
                total_rx += peer["rx_bytes"] or 0
                total_tx += peer["tx_bytes"] or 0
            if handshake and (latest is None or handshake > latest):
                latest = handshake
        data["rx_bytes"] = total_rx or None
        data["tx_bytes"] = total_tx or None
        data["latest_handshake"] = latest


def _netifd_addresses(entry: dict) -> list[str]:
    """Addresses from either the legacy ``addresses`` or modern OpenWrt
    ``ipv4-address`` / ``ipv6-address`` response keys."""
    raw = entry.get("addresses")
    if raw is None:
        raw = list(entry.get("ipv4-address", [])) + list(entry.get("ipv6-address", []))
    return [
        (a.get("address") or "")
        for a in raw
        if isinstance(a, dict) and a.get("address")
    ]


def _apply_netifd(tunnels: dict[str, dict], network_ifaces: list[dict]) -> None:
    for entry in network_ifaces:
        name = entry.get("interface")
        if not name:
            continue
        runtime = tunnels.get(name)
        if runtime is None:
            continue
        runtime["up"] = bool(entry.get("up", False))
        runtime["addresses"] = _netifd_addresses(entry)


class VpnCollector(Collector):
    name = "vpn"

    def collect(self, ctx: CollectorContext) -> list[VpnTunnel]:
        tunnels: list[VpnTunnel] = []

        wg = _parse_wg_interfaces(ctx.sh("wg show all interfaces", default=""))
        if wg:
            _enrich_wg_peers(
                wg,
                handshakes=self._wg_map(ctx, "latest-handshakes"),
                transfer=self._wg_map(ctx, "transfer"),
                keepalive=self._wg_map(ctx, "persistent-keepalive"),
            )

        network_ifaces: list[dict] = []
        try:
            dump = ctx.ubus.call("network.interface", "dump")
            network_ifaces = dump.get("interface", [])
        except Exception:  # noqa: BLE001
            pass

        _apply_netifd(wg, network_ifaces)

        for name, runtime in wg.items():
            tunnels.append(self._wg_tunnel(name, runtime))

        seen = {t.name for t in tunnels}
        for entry in network_ifaces:
            proto = entry.get("proto")
            name = entry.get("interface")
            if name and name not in seen:
                if proto == "openvpn":
                    tunnels.append(self._openvpn_from_netifd(entry))
                    seen.add(name)
                elif proto == "wireguard":
                    tunnels.append(self._wireguard_from_netifd(entry))
                    seen.add(name)

        self._collect_openvpn_config(ctx, tunnels, seen)

        tailscale = self._tailscale(ctx)
        if tailscale:
            tunnels.append(tailscale)

        ipsec = self._ipsec(ctx)
        if ipsec:
            tunnels.append(ipsec)

        zerotier = self._zerotier(ctx)
        if zerotier:
            tunnels.append(zerotier)

        return tunnels

    @staticmethod
    def _wg_map(ctx: CollectorContext, subcommand: str) -> dict[tuple[str, str], list[str]]:
        return _parse_wg_peer_map(
            ctx.sh(f"wg show all {subcommand} 2>/dev/null", default="")
        )

    @staticmethod
    def _wg_tunnel(name: str, runtime: dict) -> VpnTunnel:
        peers = runtime.get("peers", [])
        return VpnTunnel(
            name=name,
            kind="wireguard",
            up=bool(runtime.get("up", False)),
            public_key=runtime.get("public_key"),
            listen_port=runtime.get("listen_port"),
            addresses=runtime.get("addresses", []),
            peer_count=len(peers),
            rx_bytes=runtime.get("rx_bytes"),
            tx_bytes=runtime.get("tx_bytes"),
            detail={
                "latest_handshake": runtime.get("latest_handshake"),
                "peers": [
                    {
                        "public_key": p["public_key"],
                        "endpoint": p.get("endpoint"),
                        "allowed_ips": p.get("allowed_ips", []),
                        "latest_handshake": p.get("latest_handshake"),
                        "persistent_keepalive": p.get("persistent_keepalive"),
                        "rx_bytes": p.get("rx_bytes"),
                        "tx_bytes": p.get("tx_bytes"),
                    }
                    for p in peers
                ],
            },
        )

    @staticmethod
    def _openvpn_from_netifd(entry: dict) -> VpnTunnel:
        return VpnTunnel(
            name=entry["interface"],
            kind="openvpn",
            up=bool(entry.get("up", False)),
            addresses=_netifd_addresses(entry),
            detail={"mode": "tunnel"},
        )

    @staticmethod
    def _wireguard_from_netifd(entry: dict) -> VpnTunnel:
        """A WireGuard interface netifd reports but ``wg`` produced no runtime
        state for (tool missing, interface down, or first run). Keeping it in
        the snapshot lets the UI distinguish *configured-but-inactive* from
        *never configured*."""
        return VpnTunnel(
            name=entry["interface"],
            kind="wireguard",
            up=bool(entry.get("up", False)),
            addresses=_netifd_addresses(entry),
            detail={"peers": [], "state": "configured-but-inactive"},
        )

    def _collect_openvpn_config(
        self, ctx: CollectorContext, tunnels: list[VpnTunnel], seen: set[str]
    ) -> None:
        sections: dict[str, dict[str, str]] = {}
        for line in ctx.sh("uci show openvpn", default="").splitlines():
            line = line.strip()
            if not line.startswith("openvpn.") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            rest = key[len("openvpn.") :]
            if "." in rest:
                section, option = rest.split(".", 1)
            else:
                section, option = rest, ""
            if option:
                sections.setdefault(section, {})[option] = value.strip("'")
        for name, opts in sections.items():
            if name in seen or name == "@openvpn[0]":
                continue
            # A config-only instance has no live netifd interface, so it is
            # *configured* (``enabled`` from UCI) but not observed running.
            # Reporting ``up`` from ``enabled`` would show a configured-but-
            # stopped tunnel as active.
            tunnels.append(
                VpnTunnel(
                    name=name,
                    kind="openvpn",
                    up=False,
                    enabled=opts.get("enabled") != "0",
                    endpoint=f"{opts.get('remote')}:{opts.get('port')}"
                    if opts.get("remote")
                    else None,
                    version=None,
                    detail={
                        "mode": opts.get("mode"),
                        "role": "server" if opts.get("mode") == "server" else "client",
                        "device": opts.get("dev"),
                        "local": opts.get("local"),
                        "remote": opts.get("remote"),
                        "port": opts.get("port"),
                        "state": "configured-but-inactive",
                    },
                )
            )

    @staticmethod
    def _tailscale(ctx: CollectorContext) -> VpnTunnel | None:
        if not ctx.sh("command -v tailscale >/dev/null 2>&1 && echo yes", default=""):
            return None
        raw = ctx.sh("tailscale status --json 2>/dev/null", default="")
        if not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            return None
        self_info = data.get("self") or {}
        dns_name = (self_info.get("DNSName") or "").strip().rstrip(".")
        hostname = (dns_name.split(".")[0] or self_info.get("HostName") or "tailscale")
        tailnet = dns_name
        if ".ts.net" in tailnet:
            tailnet = tailnet.split(".ts.net", 1)[0]
            _, _, tailnet = tailnet.partition(".")
        elif "." in tailnet:
            tailnet = tailnet.split(".", 1)[1]
        ips = [ip for ip in (self_info.get("TailscaleIPs") or []) if isinstance(ip, str)]
        version = (data.get("Version") or "").strip() or None
        return VpnTunnel(
            name="tailscale",
            kind="tailscale",
            up=bool(self_info.get("Online", True)),
            enabled=True,
            addresses=ips,
            version=version,
            detail={
                "hostname": hostname,
                "tailnet": tailnet,
                "ip": ips[0] if ips else None,
                "online": bool(self_info.get("Online", True)),
                "exit_node": bool(self_info.get("ExitNode", False)),
            },
        )

    @staticmethod
    def _ipsec(ctx: CollectorContext) -> VpnTunnel | None:
        if not ctx.sh("command -v ipsec >/dev/null 2>&1 && echo yes", default=""):
            return None
        status = ctx.sh("ipsec statusall 2>/dev/null", default="")
        if not status.strip():
            return None
        # The count comes from the summary line ``Security Associations (N up,
        # M connecting)`` — counting matching *lines* would treat the summary
        # itself as one connection even when nothing is up.
        match = _IPSEC_SUMMARY.search(status)
        conns = int(match.group(1)) if match else 0
        # The daemon may be installed and running while zero Security
        # Associations are up: "up" means an active tunnel, not merely that
        # ``ipsec statusall`` produced output.
        active = conns > 0
        return VpnTunnel(
            name="ipsec",
            kind="ipsec",
            up=active,
            enabled=True,
            peer_count=conns,
            detail={
                "connections": conns,
                "status": "up" if active else "configured-but-inactive",
                "peers": conns,
            },
        )

    @staticmethod
    def _zerotier(ctx: CollectorContext) -> VpnTunnel | None:
        if not ctx.sh("command -v zerotier-cli >/dev/null 2>&1 && echo yes", default=""):
            return None
        output = ctx.sh("zerotier-cli listnetworks 2>/dev/null", default="")
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        networks = []
        for line in lines:
            parts = line.split()
            if len(parts) < 4 or not parts[0].isdigit():
                continue
            nwid = parts[1]
            status = parts[3]
            assigned = next((p for p in parts if "/" in p and "." in p), None)
            networks.append({"network_id": nwid, "status": status, "assigned_ip": assigned})
        if not networks:
            return None
        return VpnTunnel(
            name="zerotier",
            kind="zerotier",
            up=True,
            enabled=True,
            peer_count=len(networks),
            detail={"networks": networks},
        )


__all__ = ["VpnCollector"]