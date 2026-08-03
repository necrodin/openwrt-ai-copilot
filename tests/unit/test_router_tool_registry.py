"""Router Tool registry tests: registration, resolution, duplicates, unknowns."""

from __future__ import annotations

import pytest

from app.services.router_tool_registry import (
    DuplicateRouterToolError,
    RouterToolRegistry,
    UnknownRouterToolError,
)


def _registry() -> RouterToolRegistry:
    registry = RouterToolRegistry()
    registry.register("system", lambda: {"hostname": "demo-router"})
    registry.register("cpu", lambda: {"usage_percent": 10})
    return registry


def test_register_and_resolve() -> None:
    registry = _registry()
    assert registry.resolve("system")() == {"hostname": "demo-router"}
    assert registry.resolve("cpu")() == {"usage_percent": 10}


def test_available_lists_registered_names() -> None:
    registry = _registry()
    assert registry.available == ["system", "cpu"]


def test_available_empty_for_new_registry() -> None:
    assert RouterToolRegistry().available == []


def test_duplicate_registration_rejected() -> None:
    registry = _registry()
    with pytest.raises(DuplicateRouterToolError):
        registry.register("system", lambda: None)


def test_unknown_tool_raises_clear_error() -> None:
    registry = _registry()
    with pytest.raises(UnknownRouterToolError, match="unknown router tool: reboot"):
        registry.resolve("reboot")
