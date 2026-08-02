"""OpenWrt knowledge sources.

:class:`OpenWrtKnowledgeSource` is a catalog of the OpenWrt knowledge domains
that future RAG will draw from. Each topic declares its canonical reference
material (documentation page / manual), related UCI config files, and package
names. A single source instance can be scoped to any subset of topics via
``topics=`` (default: all twelve).
"""

from __future__ import annotations

from knowledge.errors import KnowledgeSourceError
from knowledge.protocols import KnowledgeSource

#: name → metadata for the twelve OpenWrt knowledge domains.
OPENWRT_TOPICS: dict[str, dict[str, object]] = {
    "openwrt-wiki": {
        "description": "The official OpenWrt wiki and how-to documentation.",
        "reference": "https://openwrt.org/docs/start",
        "formats": ["html", "markdown"],
        "packages": [],
        "config_files": [],
        "tags": ["openwrt", "documentation", "howto"],
    },
    "luci-docs": {
        "description": "LuCI — the OpenWrt web interface, its REST API, and extension docs.",
        "reference": "https://openwrt.org/docs/techref/luci",
        "formats": ["html", "markdown"],
        "packages": ["luci", "luci-base", "luci-app-*"],
        "config_files": [],
        "tags": ["luci", "web", "ui", "rpc"],
    },
    "wireguard": {
        "description": "WireGuard VPN configuration on OpenWrt.",
        "reference": "https://openwrt.org/docs/guide-user/services/vpn/wireguard/start",
        "formats": ["html", "markdown"],
        "packages": ["wireguard-tools", "kmod-wireguard"],
        "config_files": ["/etc/config/network", "/etc/config/firewall"],
        "tags": ["vpn", "wireguard", "network", "tunnel"],
    },
    "openvpn": {
        "description": "OpenVPN client/server configuration on OpenWrt.",
        "reference": "https://openwrt.org/docs/guide-user/services/vpn/openvpn/start",
        "formats": ["html", "markdown"],
        "packages": ["openvpn", "openvpn-openssl"],
        "config_files": ["/etc/config/openvpn"],
        "tags": ["vpn", "openvpn", "network", "tunnel"],
    },
    "nftables": {
        "description": "nftables firewall configuration on OpenWrt.",
        "reference": "https://openwrt.org/docs/guide-user/firewall/fw3/configuration/fw3_config_nftables",
        "formats": ["html", "markdown"],
        "packages": ["nftables", "kmod-nft-*"],
        "config_files": ["/etc/config/firewall", "/etc/nftables.d"],
        "tags": ["firewall", "nftables", "security"],
    },
    "iptables": {
        "description": "iptables (legacy) firewall configuration on OpenWrt.",
        "reference": "https://openwrt.org/docs/guide-user/firewall/fw3/configuration",
        "formats": ["html", "markdown"],
        "packages": ["iptables", "iptables-mod-*"],
        "config_files": ["/etc/config/firewall"],
        "tags": ["firewall", "iptables", "security"],
    },
    "dnsmasq": {
        "description": "dnsmasq DNS/DHCP server configuration on OpenWrt.",
        "reference": "https://openwrt.org/docs/guide-user/base-system/dhcp/dnsmasq",
        "formats": ["html", "markdown"],
        "packages": ["dnsmasq", "dnsmasq-full"],
        "config_files": ["/etc/config/dhcp", "/etc/dnsmasq.conf"],
        "tags": ["dns", "dhcp", "dnsmasq"],
    },
    "odhcpd": {
        "description": "odhcpd — the OpenWrt DHCPv6 / RA / NDP daemon.",
        "reference": "https://openwrt.org/docs/guide-user/base-system/dhcp/odhcpd",
        "formats": ["html", "markdown"],
        "packages": ["odhcpd"],
        "config_files": ["/etc/config/dhcp"],
        "tags": ["dhcpv6", "ipv6", "ra", "ndp"],
    },
    "sqm": {
        "description": "SQM (Smart Queue Management) — CAKE/fq_codel traffic shaping.",
        "reference": "https://openwrt.org/docs/guide-user/network/traffic-shaping/sqm",
        "formats": ["html", "markdown"],
        "packages": ["sqm-scripts", "kmod-sched-cake"],
        "config_files": ["/etc/config/sqm"],
        "tags": ["qos", "traffic-shaping", "cake", "fq_codel"],
    },
    "mwan3": {
        "description": "mwan3 — multi-WAN load balancing and failover.",
        "reference": "https://openwrt.org/docs/guide-user/network/wan/multiwan/mwan3",
        "formats": ["html", "markdown"],
        "packages": ["mwan3"],
        "config_files": ["/etc/config/mwan3", "/etc/config/network"],
        "tags": ["mwan", "load-balancing", "failover", "wan"],
    },
    "uci": {
        "description": "UCI — the Unified Configuration Interface: syntax, sections, and CLI.",
        "reference": "https://openwrt.org/docs/techref/uci",
        "formats": ["html", "markdown"],
        "packages": ["uci"],
        "config_files": ["/etc/config/*"],
        "tags": ["uci", "configuration", "cli"],
    },
    "package-docs": {
        "description": "Per-package documentation shipped inside OpenWrt images.",
        "reference": "/usr/share/doc",
        "formats": ["txt", "markdown", "html"],
        "packages": ["*"],
        "config_files": [],
        "tags": ["packages", "documentation"],
    },
}


class OpenWrtKnowledgeSource(KnowledgeSource):
    """Catalog of OpenWrt knowledge domains.

    ``topics=None`` exposes all twelve; otherwise only the requested topic ids.
    Documents can be loaded from local paths (via ``FileLoader``) or URLs (via
    ``HttpLoader``) — the source itself only manages the catalog.
    """

    source_type = "openwrt"

    def __init__(self, topics: list[str] | None = None, base_path: str | None = None) -> None:
        self._topics = list(topics) if topics else list(OPENWRT_TOPICS)
        self._base_path = base_path
        self.formats = {
            str(fmt) for topic in self._topics for fmt in OPENWRT_TOPICS[topic].get("formats", [])
        }

    @property
    def id(self) -> str:
        return "openwrt"

    @property
    def description(self) -> str:
        return "OpenWrt knowledge domains: wiki, LuCI, VPN, firewall, DNS/DHCP, QoS, UCI, packages."

    def list_documents(self) -> list[str]:
        return [f"topic:{topic}" for topic in self._topics]

    def topic(self, topic_id: str) -> dict[str, object]:
        if topic_id not in OPENWRT_TOPICS:
            raise KnowledgeSourceError(f"Unknown OpenWrt topic {topic_id!r}")
        return dict(OPENWRT_TOPICS[topic_id])

    def topics(self) -> dict[str, dict[str, object]]:
        return {topic_id: self.topic(topic_id) for topic_id in self._topics}

    def load(self, reference: str) -> bytes:
        raise KnowledgeSourceError(
            "OpenWrtKnowledgeSource is a catalog; point a loader (file/http) at a "
            f"topic's reference ({reference!r}) to fetch raw content."
        )


__all__ = ["OPENWRT_TOPICS", "OpenWrtKnowledgeSource"]
