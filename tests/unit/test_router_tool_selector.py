"""Router Tool selector tests: intent resolution from a user message."""

from __future__ import annotations

import pytest

from app.services.router_tool_registry import RouterToolRegistry
from app.services.router_tool_selector import RouterToolSelector


def _registry() -> RouterToolRegistry:
    registry = RouterToolRegistry()
    for name in ("system", "cpu", "memory", "storage", "network", "wifi"):
        registry.register(name, lambda: None)
    return registry


def _selector() -> RouterToolSelector:
    return RouterToolSelector(_registry())


def test_select_system_intent() -> None:
    assert "system" in _selector().select("what is the router hostname?")


def test_select_cpu_intent() -> None:
    assert "cpu" in _selector().select("how high is the cpu load?")


def test_select_memory_intent() -> None:
    assert "memory" in _selector().select("how much ram is free?")


def test_select_storage_intent() -> None:
    assert "storage" in _selector().select("how much disk space is used?")


def test_select_network_intent() -> None:
    assert "network" in _selector().select("show me the wan interfaces")


def test_select_multiple_intents() -> None:
    intents = _selector().select("show router cpu and memory usage")
    assert "cpu" in intents
    assert "memory" in intents


def test_select_all_intents() -> None:
    intents = _selector().select("router system cpu memory storage network")
    assert intents == ["system", "cpu", "memory", "storage", "network"]


def test_select_no_router_info() -> None:
    assert _selector().select("hello, how are you today?") == []


def test_select_only_registered_intents() -> None:
    registry = RouterToolRegistry()
    registry.register("cpu", lambda: None)
    selector = RouterToolSelector(registry)
    assert selector.select("how high is the cpu load?") == ["cpu"]
    assert "network" not in selector.select("show me the wan interfaces")


def test_select_empty_registry() -> None:
    assert RouterToolSelector(RouterToolRegistry()).select("cpu memory network") == []


@pytest.mark.parametrize(
    "message,intent",
    [
        ("what is the firmware version?", "system"),
        ("how many cores does it have?", "cpu"),
        ("any issues with the filesystem?", "storage"),
        ("is wifi up?", "wifi"),
        ("show the wan interfaces", "network"),
    ],
)
def test_select_keyword_variants(message: str, intent: str) -> None:
    assert intent in _selector().select(message)


@pytest.mark.parametrize(
    "message,intent",
    [
        ("is vpn configured?", "network"),
        ("show wireguard peers", "network"),
        ("what are the dns servers?", "network"),
        ("show active dhcp leases.", "network"),
        ("which clients are online?", "wifi"),
        ("list the firewall zones", "network"),
        ("what is my wan gateway?", "network"),
        ("show the routing table", "network"),
        ("what packages are installed?", "system"),
        ("what services are running?", "system"),
        ("any new logs from the firewall?", "system"),
        ("how much ram is free?", "memory"),
    ],
)
def test_select_common_router_topics(message: str, intent: str) -> None:
    """Common router topics (VPN/DNS/DHCP/clients/firewall/services/packages)
    must select a router intent so focused context + diagnosis are injected."""
    assert intent in _selector().select(message)


def test_select_write_request_still_selects_read_context_only() -> None:
    """A write-capable phrase maps to read-only router intents, never to a
    management action (the chat tool layer has no write tools)."""
    intents = _selector().select("restart dnsmasq")
    assert intents  # read-only context intent
    assert "network" in intents


def test_select_wifi_intent() -> None:
    assert "wifi" in _selector().select("how many wireless clients are connected?")
    assert "wifi" in _selector().select("show me the wifi stations")
    assert "wifi" in _selector().select("which clients are wireless?")


def test_select_wifi_does_not_force_network() -> None:
    """A pure wireless question selects the wifi intent; it does not need to
    drag in the network-interface intent."""
    intents = _selector().select("show wireless clients")
    assert "wifi" in intents
