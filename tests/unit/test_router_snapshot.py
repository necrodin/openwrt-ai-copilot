"""Router snapshot tests: combining tool results, null sections, cache reuse."""

from __future__ import annotations

import pytest

from app.services.router_context_cache import RouterContextCache
from app.services.router_snapshot import RouterSnapshot, RouterSnapshotService
from app.services.router_tool_executor import RouterToolExecutor
from app.services.router_tool_registry import RouterToolRegistry


def _registry() -> RouterToolRegistry:
    registry = RouterToolRegistry()
    registry.register("system", lambda: {"hostname": "demo-router", "model": "RT-1"})
    registry.register("cpu", lambda: {"usage_percent": 12.0, "cores": 4})
    registry.register("memory", lambda: {"total_kb": 262144, "used_kb": 131072})
    registry.register("storage", lambda: [{"mountpoint": "/overlay", "filesystem": "ext4"}])
    registry.register("network", lambda: [{"name": "br-lan", "up": True, "proto": "static"}])
    return registry


def _executor(registry: RouterToolRegistry | None = None) -> RouterToolExecutor:
    return RouterToolExecutor(registry or _registry())


def _service() -> RouterSnapshotService:
    return RouterSnapshotService(RouterContextCache())


def test_build_combines_tool_results() -> None:
    snapshot = _service().build(
        _executor(),
        "s1",
        ["system", "cpu", "memory", "storage", "network"],
    )
    assert isinstance(snapshot, RouterSnapshot)
    assert snapshot.system == {"hostname": "demo-router", "model": "RT-1"}
    assert snapshot.cpu == {"usage_percent": 12.0, "cores": 4}
    assert snapshot.memory == {"total_kb": 262144, "used_kb": 131072}
    assert snapshot.storage == [{"mountpoint": "/overlay", "filesystem": "ext4"}]
    assert snapshot.network == [{"name": "br-lan", "up": True, "proto": "static"}]


def test_build_missing_sections_are_none() -> None:
    snapshot = _service().build(_executor(), "s1", ["system"])
    assert snapshot.system is not None
    assert snapshot.cpu is None
    assert snapshot.memory is None
    assert snapshot.storage is None
    assert snapshot.network is None
    assert snapshot.wifi is None


def test_build_failed_section_is_none() -> None:
    registry = RouterToolRegistry()
    registry.register("system", lambda: {"hostname": "demo-router"})

    def boom() -> dict:
        raise RuntimeError("collector failed")

    registry.register("cpu", boom)
    snapshot = _service().build(
        _executor(registry),
        "s1",
        ["system", "cpu"],
    )
    assert snapshot.system is not None
    assert snapshot.cpu is None


def test_build_does_not_execute_cached_tools_twice() -> None:
    calls: list[str] = []
    registry = RouterToolRegistry()

    def tracking(name: str):
        def tool() -> dict:
            calls.append(name)
            return {"name": name}

        return tool

    registry.register("storage", tracking("storage"))
    service = _service()
    executor = _executor(registry)
    service.build(executor, "s1", ["storage"])
    service.build(executor, "s1", ["storage"])
    assert calls == ["storage"]


def test_build_reuses_cache_across_sessions_independently() -> None:
    service = _service()
    executor = _executor()
    first = service.build(executor, "s1", ["system"])
    second = service.build(executor, "s2", ["system"])
    assert first.system == second.system


def test_snapshot_is_immutable() -> None:
    snapshot = RouterSnapshot(system={"hostname": "demo-router"})
    with pytest.raises(AttributeError):
        snapshot.system = {"hostname": "other"}  # type: ignore[misc]


def test_snapshot_to_dict_maps_null_sections() -> None:
    snapshot = RouterSnapshot(system={"hostname": "demo-router"})
    payload = snapshot.to_dict()
    assert payload["system"] == {"hostname": "demo-router"}
    assert payload["cpu"] is None
    assert payload["storage"] is None
    assert payload["wifi"] is None


def test_render_markdown_returns_none_when_empty() -> None:
    assert RouterSnapshotService().render_markdown(RouterSnapshot()) is None


def test_render_markdown_renders_selected_sections() -> None:
    snapshot = RouterSnapshot(
        system={"hostname": "demo-router", "model": "RT-1", "board": "rt1", "firmware": "24.10"},
        cpu={"usage_percent": 12.0, "cores": 4},
    )
    markdown = _service().render_markdown(snapshot, intents=["system", "cpu"])
    assert markdown is not None
    assert "## Router" in markdown
    assert "- Hostname: demo-router" in markdown
    assert "## CPU" in markdown
    assert "Memory" not in markdown
