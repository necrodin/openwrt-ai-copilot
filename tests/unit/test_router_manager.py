"""Router manager tests: registration, listing, resolution, default, validation."""

from __future__ import annotations

import pytest

from app.services.router_manager import (
    DuplicateRouterError,
    RegisteredRouter,
    RouterManager,
    UnknownRouterError,
)
from app.services.router_tool import RouterTool


def _tool(hostname: str) -> RouterTool:
    class FakeSnapshot:
        def __init__(self, hostname: str) -> None:
            self.snapshot = None
            self._hostname = hostname

        def latest(self):
            if self.snapshot is None:
                return None
            return self.snapshot

    return RouterTool(FakeSnapshot(hostname).latest)


def test_register_and_list() -> None:
    manager = RouterManager()
    manager.register("router-a", _tool("a"))
    manager.register("router-b", _tool("b"))
    assert manager.list() == ["router-a", "router-b"]


def test_first_registered_becomes_default() -> None:
    manager = RouterManager()
    manager.register("router-a", _tool("a"))
    manager.register("router-b", _tool("b"))
    assert manager.default.router_id == "router-a"


def test_explicit_default_wins() -> None:
    manager = RouterManager()
    manager.register("router-a", _tool("a"))
    manager.register("router-b", _tool("b"), default=True)
    assert manager.default.router_id == "router-b"


def test_register_returns_registered_router() -> None:
    manager = RouterManager()
    router = manager.register("router-a", _tool("a"))
    assert isinstance(router, RegisteredRouter)
    assert router.router_id == "router-a"
    assert router.tool is not None
    assert router.registry is not None
    assert router.executor is not None
    assert router.cache is not None
    assert router.snapshot_service is not None


def test_resolve_by_identifier() -> None:
    manager = RouterManager()
    manager.register("router-a", _tool("a"))
    manager.register("router-b", _tool("b"))
    assert manager.resolve("router-b").router_id == "router-b"


def test_resolve_unknown_router_raises() -> None:
    manager = RouterManager()
    manager.register("router-a", _tool("a"))
    with pytest.raises(UnknownRouterError):
        manager.resolve("router-unknown")


def test_default_raises_when_no_router() -> None:
    manager = RouterManager()
    with pytest.raises(UnknownRouterError):
        manager.default  # noqa: B018


def test_duplicate_registration_raises() -> None:
    manager = RouterManager()
    manager.register("router-a", _tool("a"))
    with pytest.raises(DuplicateRouterError):
        manager.register("router-a", _tool("a"))


def test_each_router_has_isolated_cache_and_executor() -> None:
    manager = RouterManager()
    first = manager.register("router-a", _tool("a"))
    second = manager.register("router-b", _tool("b"))
    assert first.cache is not second.cache
    assert first.executor is not second.executor
    assert first.registry is not second.registry
    assert first.snapshot_service is not second.snapshot_service
