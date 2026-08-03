"""Router Tool selector: decides which Router Tools a chat request needs.

The selector inspects the user's message and maps it to the read-only tool
intents that should be executed. When no router information is required it
returns an empty list so the chat pipeline can skip Router Tool execution
entirely.
"""

from __future__ import annotations

ToolIntent = str  # one of: system, cpu, memory, storage, network

_SUPPORTED_INTENTS = ("system", "cpu", "memory", "storage", "network")

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
    ),
    "cpu": ("cpu", "load", "processor", "cores"),
    "memory": ("memory", "ram"),
    "storage": ("storage", "disk", "mount", "filesystem", "space"),
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
        "wifi",
        "wireless",
    ),
}


class RouterToolSelector:
    """Maps a user message to the Router Tool intents it requires."""

    def select(self, message: str) -> list[ToolIntent]:
        """Return the tool intents required for ``message`` (may be empty)."""
        text = message.lower()
        intents = [
            intent
            for intent in _SUPPORTED_INTENTS
            if any(keyword in text for keyword in _KEYWORDS[intent])
        ]
        return intents
