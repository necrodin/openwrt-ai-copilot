"""Router Tool tests: provider-independent read-only getters over the snapshot."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.schemas.dashboard import DashboardUpdate
from app.services.demo_source import build_simulated_snapshot
from app.services.router_tool import RouterTool


def _update() -> DashboardUpdate:
    return DashboardUpdate(
        type="update",
        sequence=1,
        sent_at=datetime.now(UTC),
        source="simulated",
        device_id="demo-router",
        connected=True,
        snapshot=build_simulated_snapshot(),
    )


_MISSING = object()


def _tool(update: object = _MISSING) -> RouterTool:
    if update is _MISSING:
        return RouterTool(lambda: _update())
    return RouterTool(lambda: None)


def test_router_tool_available_with_snapshot() -> None:
    assert _tool().available is True


def test_router_tool_unavailable_without_snapshot() -> None:
    assert _tool(None).available is False


def test_get_system_info() -> None:
    info = _tool().get_system_info()
    assert info["hostname"] != "unknown"
    assert info["model"] is not None
    assert info["firmware"] is not None
    assert info["kernel"] is not None


def test_get_system_info_empty_without_snapshot() -> None:
    assert _tool(None).get_system_info() == {}


def test_get_cpu_info() -> None:
    cpu = _tool().get_cpu_info()
    assert cpu["cores"] > 0
    assert cpu["usage_percent"] is not None


def test_get_memory_info() -> None:
    memory = _tool().get_memory_info()
    assert memory["total_kb"] > 0
    assert "used_percent" in memory


def test_get_storage_info() -> None:
    storage = _tool().get_storage_info()
    assert len(storage) > 0
    assert storage[0]["mountpoint"] == "/"


def test_get_network_info() -> None:
    network = _tool().get_network_info()
    assert len(network) > 0
    assert network[0]["name"]
    assert "ipv4" in network[0]


def test_getters_empty_without_snapshot() -> None:
    tool = _tool(None)
    assert tool.get_cpu_info() == {}
    assert tool.get_memory_info() == {}
    assert tool.get_storage_info() == []
    assert tool.get_network_info() == []


def test_getters_do_not_mutate_shared_context() -> None:
    tool = _tool()
    first = tool.get_system_info()
    second = tool.get_system_info()
    assert first == second
    first["hostname"] = "mutated"
    assert tool.get_system_info()["hostname"] != "mutated"


def test_router_tool_is_read_only() -> None:
    tool = _tool()
    with pytest.raises(AttributeError):
        tool.set_config("reboot")  # type: ignore[attr-defined]


def test_render_markdown_includes_all_sections() -> None:
    markdown = _tool().render_markdown()
    assert markdown is not None
    assert "## Router" in markdown
    assert "## CPU" in markdown
    assert "## Memory" in markdown
    assert "## Storage" in markdown
    assert "## Network Interfaces" in markdown
    assert "Hostname: demo-router" in markdown


def test_render_markdown_none_without_snapshot() -> None:
    assert _tool(None).render_markdown() is None
