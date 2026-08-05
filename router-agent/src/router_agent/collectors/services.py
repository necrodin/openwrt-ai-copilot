"""System services collector.

Detects the presence and health of the OpenWrt services users most care about
(firewall, DNS/DHCP, hostapd, SSH, VPN, QoS). For each service it reports
whether it is *configured* (present in UCI / has an init script), *enabled*
(boot-time rc symlink), and *running* (a live process or active kernel state).
All checks are read-only and best-effort — a service that is absent on a given
device is simply reported as not configured.
"""

from __future__ import annotations

from dataclasses import dataclass

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import ServiceInfo


@dataclass(frozen=True)
class _ServiceSpec:
    name: str
    #: Running-process binary names (pgrep -x), or None when state comes from
    #: a custom ``running_cmd``.
    binaries: tuple[str, ...] = ()
    #: /etc/init.d script name (None when netifd or the kernel manages it).
    init: str | None = None
    #: UCI namespace that indicates configuration exists.
    uci: str | None = None
    #: Custom command whose non-empty output means "running".
    running_cmd: str | None = None


_SERVICES = (
    _ServiceSpec(
        name="firewall", init="firewall", uci="firewall", running_cmd="nft list ruleset 2>/dev/null"
    ),
    _ServiceSpec(name="dnsmasq", binaries=("dnsmasq",), init="dnsmasq", uci="dhcp"),
    _ServiceSpec(name="odhcpd", binaries=("odhcpd",), init="odhcpd", uci="dhcp"),
    _ServiceSpec(name="hostapd", binaries=("hostapd", "wpa_supplicant"), uci="wireless"),
    _ServiceSpec(name="dropbear", binaries=("dropbear",), init="dropbear", uci="dropbear"),
    _ServiceSpec(
        name="wireguard",
        uci="network",
        running_cmd="ip -o link show type wireguard 2>/dev/null",
    ),
    _ServiceSpec(name="tailscale", binaries=("tailscaled",), init="tailscaled", uci="tailscale"),
    _ServiceSpec(name="mwan3", binaries=("mwan3",), init="mwan3", uci="mwan3"),
    _ServiceSpec(name="sqm", binaries=("sqm", "tc"), init="sqm", uci="sqm"),
)


class ServicesCollector(Collector):
    name = "services"

    def collect(self, ctx: CollectorContext) -> list[ServiceInfo]:
        services: list[ServiceInfo] = []
        for spec in _SERVICES:
            services.append(
                ServiceInfo(
                    name=spec.name,
                    running=self._running(ctx, spec),
                    enabled=self._enabled(ctx, spec),
                    configured=self._configured(ctx, spec),
                )
            )
        return services

    @staticmethod
    def _running(ctx: CollectorContext, spec: _ServiceSpec) -> bool:
        if spec.running_cmd is not None:
            return bool(ctx.sh(spec.running_cmd, default="").strip())
        if not spec.binaries:
            return False
        pgrep = " ".join(f"pgrep -x {binary} 2>/dev/null" for binary in spec.binaries)
        return bool(ctx.sh(pgrep, default="").strip())

    @staticmethod
    def _enabled(ctx: CollectorContext, spec: _ServiceSpec) -> bool:
        if spec.init is None:
            return False
        return bool(ctx.sh(f"/etc/init.d/{spec.init} enabled 2>/dev/null", default="").strip())

    @staticmethod
    def _configured(ctx: CollectorContext, spec: _ServiceSpec) -> bool:
        if spec.uci is None:
            return False
        return bool(ctx.sh(f"uci show {spec.uci} 2>/dev/null", default="").strip())


__all__ = ["ServicesCollector"]
