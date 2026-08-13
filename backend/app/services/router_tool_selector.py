"""Router Tool selector: decides which Router Tools a chat request needs.

The selector inspects the user's message and maps it to the read-only tool
intents that should be executed. Available tools come from a
:class:`RouterToolRegistry`; when no router information is required it returns
an empty list so the chat pipeline can skip Router Tool execution entirely.
"""

from __future__ import annotations

from app.services.router_tool_registry import RouterToolRegistry

ToolIntent = str  # one of: system, cpu, memory, storage, network, wifi

_KEYWORDS: dict[ToolIntent, tuple[str, ...]] = {
    "system": (
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
        # Services / software / runtime info.
        "services",
        "service",
        "process",
        "processes",
        "package",
        "packages",
        "installed",
        "temperature",
        "logs",
        "logread",
        "timezone",
    ),
    "cpu": ("cpu", "load", "processor", "cores"),
    "memory": ("memory", "ram", "swap"),
    "storage": (
        "storage",
        "disk",
        "mount",
        "filesystem",
        "filesystems",
        "space",
        "capacity",
    ),
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
        # Router network topics (VPN / DNS / DHCP / firewall / routing).
        # ``route``/``lease``/``nat`` are avoided: they substring-match
        # unrelated words (``router``, ``please``, ``international``).
        "vpn",
        "openvpn",
        "wireguard",
        "dns",
        "dnsmasq",
        "dhcp",
        "leases",
        "firewall",
        "gateway",
        "routing",
        "neighbor",
    ),
    "wifi": (
        "wifi",
        "wireless",
        "clients",
        "client",
        "stations",
        "station",
        "ssid",
    ),
}


class RouterToolSelector:
    """Maps a user message to the Router Tool intents it requires."""

    def __init__(self, registry: RouterToolRegistry | None = None) -> None:
        self._registry = registry if registry is not None else RouterToolRegistry()

    def select(self, message: str) -> list[ToolIntent]:
        """Return the tool intents required for ``message`` (may be empty).

        Only intents registered in the underlying registry are considered.
        """
        text = message.lower()
        intents = [
            name
            for name in self._registry.available
            if any(keyword in text for keyword in _KEYWORDS.get(name, ()))
        ]
        return intents
