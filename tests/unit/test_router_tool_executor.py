"""Router Tool executor tests: orchestration, ordering, failure tolerance."""

from __future__ import annotations

from app.services.router_tool_executor import RouterToolExecutor, RouterToolResult
from app.services.router_tool_registry import RouterToolRegistry


def _registry() -> RouterToolRegistry:
    registry = RouterToolRegistry()
    registry.register("system", lambda: {"hostname": "demo-router"})
    registry.register("cpu", lambda: {"usage_percent": 10})
    registry.register("network", lambda: [{"name": "br-lan", "up": True}])
    return registry


def test_execute_single_request() -> None:
    results = RouterToolExecutor(_registry()).execute(["system"])
    assert len(results) == 1
    assert results[0].name == "system"
    assert results[0].ok is True
    assert results[0].result == {"hostname": "demo-router"}


def test_execute_multiple_requests_preserves_order() -> None:
    results = RouterToolExecutor(_registry()).execute(["system", "cpu", "network"])
    assert [r.name for r in results] == ["system", "cpu", "network"]
    assert all(r.ok for r in results)


def test_execute_empty_requests() -> None:
    assert RouterToolExecutor(_registry()).execute([]) == []


def test_execute_continues_after_tool_failure() -> None:
    registry = _registry()

    def boom() -> dict:
        raise RuntimeError("collector failed")

    registry.register("storage", boom)
    results = RouterToolExecutor(registry).execute(["system", "storage", "network"])
    assert [r.name for r in results] == ["system", "storage", "network"]
    assert results[0].ok is True
    assert results[1].ok is False
    assert results[1].error == "collector failed"
    assert results[2].ok is True


def test_execute_never_raises_for_unknown_tool() -> None:
    results = RouterToolExecutor(_registry()).execute(["reboot"])
    assert len(results) == 1
    assert results[0].name == "reboot"
    assert results[0].ok is False
    assert results[0].error is not None


def test_execute_returns_structured_results() -> None:
    results = RouterToolExecutor(_registry()).execute(["system", "nope"])
    assert all(isinstance(r, RouterToolResult) for r in results)
    payload = [r.to_dict() for r in results]
    assert payload[0]["name"] == "system"
    assert payload[0]["ok"] is True
    assert payload[1]["name"] == "nope"
    assert payload[1]["ok"] is False
