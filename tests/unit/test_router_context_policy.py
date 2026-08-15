"""Copilot focused-context policy tests (M2 context minimization).

Verifies deterministic intent → section routing: the model prompt receives only
the snapshot sections a question actually needs (pruned), sensitive data is
excluded unless explicitly requested, and unknown questions get a small bounded
fallback — never the full raw snapshot.
"""

from __future__ import annotations

import pytest

from app.services.demo_source import build_simulated_snapshot
from app.services.router_context_policy import (
    FALLBACK_SECTIONS,
    build_focused_context,
    select_sections,
)

SNAPSHOT = build_simulated_snapshot()

# Sentinel values that must never reach a focused context unless their section
# is explicitly requested.
_SENTINEL = "SUPER-SECRET-VALUE-xyz"


def _snapshot_with_sentinels():
    snap = build_simulated_snapshot()
    if snap.logs.entries:
        snap.logs.entries[0].message = f"leak {_SENTINEL} in log"
    if snap.packages:
        snap.packages[0].description = f"leak {_SENTINEL} in package metadata"
        snap.packages[0].name = f"pkg-{_SENTINEL}"
    if snap.arp:
        snap.arp[0].mac = "aa:bb:cc:11:22:33"
    if snap.clients:
        snap.clients[0].hostname = f"host-{_SENTINEL}"
    if snap.dhcp and snap.dhcp.static_leases:
        snap.dhcp.static_leases[0].hostname = f"static-{_SENTINEL}"
    snap.client_media["aa:bb:cc:11:22:33"] = "wireless"
    return snap


def _availability(ctx: dict, category: str) -> str:
    """Look up a category's status inside a focused context manifest."""
    manifest = ctx["router_data_availability"]
    return next(item["status"] for item in manifest if item["category"] == category)


def test_wan_question_excludes_unrelated_sections() -> None:
    sections = select_sections("what is my WAN IP?")
    assert "network" in sections
    assert "network_status" in sections
    assert not sections & {"firewall", "logs", "packages", "vpn", "clients"}
    ctx = build_focused_context(SNAPSHOT, sections)
    assert set(ctx) - {"router_data_availability"} == {"network", "network_status"}
    assert _availability(ctx, "public_ip") in ("available", "unknown")
    assert _availability(ctx, "dns") == "available"


def test_wireless_question_includes_wifi_and_clients() -> None:
    sections = select_sections("which clients are wireless?")
    assert "wifi" in sections
    assert "clients" in sections
    ctx = build_focused_context(SNAPSHOT, sections)
    assert "wifi" in ctx
    assert "clients" in ctx
    assert "client_media" in ctx  # per-MAC medium folded in for client topics


def test_firewall_question_excludes_unrelated_sections() -> None:
    sections = select_sections("show firewall rules")
    assert sections == {"firewall"}
    ctx = build_focused_context(SNAPSHOT, sections)
    assert set(ctx) - {"router_data_availability"} == {"firewall"}


def test_vpn_question_includes_only_vpn() -> None:
    sections = select_sections("is VPN configured?")
    assert sections == {"vpn"}
    ctx = build_focused_context(SNAPSHOT, sections)
    assert set(ctx) - {"router_data_availability"} == {"vpn"}


def test_packages_question_includes_only_packages() -> None:
    sections = select_sections("what packages are installed?")
    assert sections == {"packages"}
    ctx = build_focused_context(SNAPSHOT, sections)
    assert set(ctx) - {"router_data_availability"} == {"packages"}
    # Package metadata (descriptions) is pruned; only name + version are sent.
    for pkg in ctx["packages"]:
        assert set(pkg) == {"name", "version"}


def test_multi_topic_question_unions_sections() -> None:
    sections = select_sections("show cpu and memory and storage usage")
    assert {"cpu", "memory", "storage"} <= sections
    ctx = build_focused_context(SNAPSHOT, sections)
    assert {"cpu", "memory", "storage"} <= set(ctx)


def test_unknown_question_uses_bounded_fallback() -> None:
    sections = select_sections("hello there, how are you?")
    assert sections == FALLBACK_SECTIONS
    ctx = build_focused_context(SNAPSHOT, sections)
    assert set(ctx) - {"router_data_availability"} <= set(FALLBACK_SECTIONS)
    # No verbose sections in the fallback.
    assert not set(ctx) & {"firewall", "logs", "packages", "vpn", "clients", "arp"}


def test_logs_only_when_explicitly_requested() -> None:
    no_logs = select_sections("what is the cpu usage?")
    assert "logs" not in no_logs
    assert "logs" not in build_focused_context(SNAPSHOT, no_logs)

    with_logs = select_sections("show the recent firewall logs")
    assert "logs" in with_logs
    assert "logs" in build_focused_context(SNAPSHOT, with_logs)


def test_sensitive_fields_never_reach_unrelated_context() -> None:
    snap = _snapshot_with_sentinels()
    # A WAN question must not leak logs/packages/clients/DHCP data.
    ctx = build_focused_context(snap, select_sections("what is my WAN IP?"))
    serialized = str(ctx)
    assert _SENTINEL not in serialized
    assert "logs" not in ctx
    assert "packages" not in ctx
    assert "clients" not in ctx
    assert "client_media" not in ctx


def test_network_prune_strips_mac_addresses() -> None:
    snap = _snapshot_with_sentinels()
    ctx = build_focused_context(snap, select_sections("show the network interfaces"))
    assert "network" in ctx
    assert "aa:bb:cc:11:22:33" not in str(ctx["network"])


def test_client_media_excluded_for_non_client_questions() -> None:
    snap = _snapshot_with_sentinels()
    ctx = build_focused_context(snap, select_sections("what is my WAN IP?"))
    assert "client_media" not in ctx
    client_ctx = build_focused_context(snap, select_sections("which clients are online?"))
    assert "client_media" in client_ctx


@pytest.mark.parametrize(
    "question,sections",
    [
        ("what is my WAN IP?", {"network", "network_status"}),
        ("what is my LAN IP?", {"network"}),
        ("what DNS servers am I using?", {"network_status"}),
        ("how many devices are connected?", {"clients"}),
        ("show DHCP leases", {"dhcp", "clients"}),
        ("which services are running?", {"services"}),
        ("how much storage is free?", {"storage"}),
        ("how much RAM is available?", {"memory"}),
        ("what OpenWrt version am I running?", {"kernel"}),
        ("show the routing table", {"network"}),
        ("show me the wireless stations", {"wifi"}),
        ("show the recent system log", {"logs"}),
    ],
)
def test_common_router_questions_map_to_expected_sections(question: str, sections: set) -> None:
    selected = select_sections(question)
    assert selected >= sections
    # The selected sections are a small, bounded set (never the whole snapshot).
    assert len(selected) <= 6
