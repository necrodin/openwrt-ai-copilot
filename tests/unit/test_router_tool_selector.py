"""Router Tool selector tests: intent resolution from a user message."""

from __future__ import annotations

import pytest

from app.services.router_tool_selector import RouterToolSelector


def _selector() -> RouterToolSelector:
    return RouterToolSelector()


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


@pytest.mark.parametrize(
    "message,intent",
    [
        ("what is the firmware version?", "system"),
        ("how many cores does it have?", "cpu"),
        ("any issues with the filesystem?", "storage"),
        ("is wifi up?", "network"),
    ],
)
def test_select_keyword_variants(message: str, intent: str) -> None:
    assert intent in _selector().select(message)
