"""Copilot data-grounding tests.

The Copilot must answer router questions from the router data that actually
exists and must never invent values that are not in the data. These tests cover
the deterministic availability manifest (available / not_available / unknown /
error) and the composed system prompt the model actually receives.

Snapshots are built with the real ``DeviceSnapshot`` model (the same structured
shape the router agent produces) so the assertions prove the grounding layer is
driven by actual router data, not by mocked model responses.
"""

from __future__ import annotations

import re

from app.services.chat_service import SYSTEM_PROMPT, ChatService
from app.services.demo_source import build_simulated_snapshot
from app.services.router_context_policy import (
    AVAILABLE,
    ERROR,
    NOT_AVAILABLE,
    build_availability_manifest,
    build_focused_context,
    select_sections,
)
from providers.factory import ProviderManager

_IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


def _statuses(snapshot) -> dict[str, str]:
    return {entry["category"]: entry["status"] for entry in build_availability_manifest(snapshot)}


def _manifest_of(prompt: str, category: str) -> str | None:
    """Extract a category's status from the manifest embedded in a prompt."""
    import ast

    match = re.search(r"['\"]router_data_availability['\"]\s*:\s*(\[.*?\])", prompt, re.S)
    assert match, "prompt must contain the router_data_availability manifest"
    for entry in ast.literal_eval(match.group(1)):
        if entry["category"] == category:
            return entry["status"]
    return None


def _clear_network(snapshot) -> None:
    """Drop every network-derived field so no IP/interface/DNS data remains."""
    snapshot.network = []
    snapshot.network_status = None
    snapshot.routing = []
    if snapshot.dhcp is not None:
        snapshot.dhcp.dns = []


def _clear_clients(snapshot) -> None:
    """Drop every client/station field."""
    snapshot.clients = []
    snapshot.arp = []
    snapshot.neighbors = []
    snapshot.wifi.clients = []
    for radio in snapshot.wifi.radios:
        radio.station_count = 0
    snapshot.client_media = {}


def test_manifest_is_compact_status_only() -> None:
    """The manifest carries availability, never values (privacy/token bound)."""
    manifest = build_availability_manifest(build_simulated_snapshot())
    assert manifest
    for entry in manifest:
        assert set(entry) == {"category", "status"}
        assert entry["status"] in {AVAILABLE, NOT_AVAILABLE, "unknown", ERROR}


# --------------------------------------------------------------------------- #
# A. Data exists                                                               #
# --------------------------------------------------------------------------- #


def test_a_cpu_data_exists_context_carries_the_actual_value() -> None:
    snapshot = build_simulated_snapshot()
    assert _statuses(snapshot)["cpu"] == AVAILABLE
    actual = snapshot.cpu.usage_percent

    ctx = build_focused_context(snapshot, select_sections("Router'ın CPU durumu nedir?"))
    assert ctx["cpu"]["usage_percent"] == actual

    service = ChatService(ProviderManager({}), lambda: snapshot)
    request = service.compose(message="Router'ın CPU durumu nedir?", history=[])
    assert str(actual) in request.messages[0].content
    assert _manifest_of(request.messages[0].content, "cpu") == AVAILABLE


# --------------------------------------------------------------------------- #
# B. Data does not exist                                                       #
# --------------------------------------------------------------------------- #


def test_b_no_public_ip_never_invented() -> None:
    snapshot = build_simulated_snapshot()
    _clear_network(snapshot)
    assert _statuses(snapshot)["public_ip"] == NOT_AVAILABLE

    ctx = build_focused_context(snapshot, select_sections("Public IP adresim nedir?"))
    serialized = str(ctx)
    # No IP value may reach the model for a public-IP question without data.
    assert _IPV4.findall(serialized) == []
    assert _manifest_of(str(ctx), "public_ip") == NOT_AVAILABLE

    service = ChatService(ProviderManager({}), lambda: snapshot)
    request = service.compose(message="Public IP adresim nedir?", history=[])
    prompt = request.messages[0].content
    assert _manifest_of(prompt, "public_ip") == NOT_AVAILABLE
    assert "not available in the current router data" in SYSTEM_PROMPT


# --------------------------------------------------------------------------- #
# C. Client count unavailable                                                  #
# --------------------------------------------------------------------------- #


def test_c_client_count_unavailable() -> None:
    snapshot = build_simulated_snapshot()
    _clear_clients(snapshot)
    assert _statuses(snapshot)["connected_clients"] == NOT_AVAILABLE

    service = ChatService(ProviderManager({}), lambda: snapshot)
    prompt = service.system_prompt(
        build_focused_context(snapshot, select_sections("Bağlı kaç cihaz var?"))
    )
    assert _manifest_of(prompt, "connected_clients") == NOT_AVAILABLE


# --------------------------------------------------------------------------- #
# D. Disk information unavailable                                              #
# --------------------------------------------------------------------------- #


def test_d_disk_information_unavailable() -> None:
    snapshot = build_simulated_snapshot()
    snapshot.storage = []
    assert _statuses(snapshot)["disk"] == NOT_AVAILABLE

    ctx = build_focused_context(snapshot, select_sections("Disk kullanımı nedir?"))
    assert ctx.get("storage") == []
    assert _manifest_of(str(ctx), "disk") == NOT_AVAILABLE


# --------------------------------------------------------------------------- #
# E. Existing valid data                                                       #
# --------------------------------------------------------------------------- #


def test_e_dns_exists_can_report_the_actual_value() -> None:
    snapshot = build_simulated_snapshot()
    snapshot.network_status.dns = ["9.9.9.9", "1.1.1.1"]
    assert _statuses(snapshot)["dns"] == AVAILABLE

    ctx = build_focused_context(snapshot, select_sections("DNS adresleri nedir?"))
    assert "9.9.9.9" in str(ctx["network_status"]["dns"])

    service = ChatService(ProviderManager({}), lambda: snapshot)
    request = service.compose(message="DNS adresleri nedir?", history=[])
    assert "9.9.9.9" in request.messages[0].content
    assert _manifest_of(request.messages[0].content, "dns") == AVAILABLE


# --------------------------------------------------------------------------- #
# F. Mixed data                                                                #
# --------------------------------------------------------------------------- #


def test_f_mixed_available_and_missing() -> None:
    snapshot = build_simulated_snapshot()
    _clear_network(snapshot)  # no public IP, no DNS, no traffic
    snapshot.storage = []  # no disk
    statuses = _statuses(snapshot)
    assert statuses["cpu"] == AVAILABLE
    assert statuses["memory"] == AVAILABLE
    assert statuses["connected_clients"] == AVAILABLE
    assert statuses["public_ip"] == NOT_AVAILABLE
    assert statuses["dns"] == NOT_AVAILABLE
    assert statuses["disk"] == NOT_AVAILABLE

    service = ChatService(ProviderManager({}), lambda: snapshot)
    prompt = service.system_prompt(
        build_focused_context(snapshot, select_sections("CPU ve disk durumu nedir?"))
    )
    assert _manifest_of(prompt, "cpu") == AVAILABLE
    assert _manifest_of(prompt, "disk") == NOT_AVAILABLE


# --------------------------------------------------------------------------- #
# Collector failure -> error status                                            #
# --------------------------------------------------------------------------- #


def test_collector_failure_is_reported_as_error() -> None:
    from router_agent.model import CollectError

    snapshot = build_simulated_snapshot()
    snapshot.network_status = None
    snapshot.errors.append(CollectError(collector="network_status", error="boom"))
    assert _statuses(snapshot)["dns"] == ERROR

    snapshot2 = build_simulated_snapshot()
    snapshot2.cpu = None
    snapshot2.errors.append(CollectError(collector="cpu", error="boom"))
    assert _statuses(snapshot2)["cpu"] == ERROR


# --------------------------------------------------------------------------- #
# Prompt-level guarantees                                                      #
# --------------------------------------------------------------------------- #


def test_system_prompt_grounding_rules_present() -> None:
    assert "router_data_availability" in SYSTEM_PROMPT
    assert "not_available" in SYSTEM_PROMPT
    assert "not available in the current router data" in SYSTEM_PROMPT
    assert "reuse a value from an earlier conversation" in SYSTEM_PROMPT


def test_no_router_state_prompt_says_data_unavailable() -> None:
    service = ChatService(ProviderManager({}), lambda: None)
    prompt = service.system_prompt()
    assert "No router state is available" in prompt
    assert "do not invent any values" in prompt
