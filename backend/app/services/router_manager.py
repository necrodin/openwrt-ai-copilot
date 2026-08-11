"""Multi-router management for the Router Tool layer.

A :class:`RouterManager` owns the set of configured routers, each backed by its
own :class:`RouterTool` instance and dedicated tool-layer instances (registry,
selector, detector, executor, cache, snapshot service). The manager registers
routers, lists them, resolves them by identifier, exposes a default router, and
validates unknown router ids. Everything is kept in-memory; no persistence is
introduced.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.services.router_context_cache import RouterContextCache
from app.services.router_intent_detector import RouterIntentDetector
from app.services.router_snapshot import RouterSnapshotService
from app.services.router_tool import RouterTool
from app.services.router_tool_executor import RouterToolExecutor
from app.services.router_tool_registry import RouterToolRegistry
from app.services.router_tool_selector import RouterToolSelector


class UnknownRouterError(Exception):
    """Raised when a router id cannot be resolved."""


class DuplicateRouterError(Exception):
    """Raised when a router id is registered more than once."""


@dataclass
class RegisteredRouter:
    """A registered router and the tool-layer instances bound to it."""

    router_id: str
    tool: RouterTool
    registry: RouterToolRegistry
    selector: RouterToolSelector
    detector: RouterIntentDetector
    executor: RouterToolExecutor
    cache: RouterContextCache
    snapshot_service: RouterSnapshotService


class RouterManager:
    """Registers and resolves routers for the chat pipeline."""

    def __init__(self) -> None:
        self._routers: dict[str, RegisteredRouter] = {}
        self._default_id: str | None = None

    @staticmethod
    def build_registry(router_tool: RouterTool | None) -> RouterToolRegistry:
        """Build a registry of read-only Router Tools from ``router_tool``."""
        registry = RouterToolRegistry()
        if router_tool is not None:
            registry.register("system", router_tool.get_system_info)
            registry.register("cpu", router_tool.get_cpu_info)
            registry.register("memory", router_tool.get_memory_info)
            registry.register("storage", router_tool.get_storage_info)
            registry.register("network", router_tool.get_network_info)
        return registry

    def register(
        self,
        router_id: str,
        router_tool: RouterTool,
        *,
        default: bool = False,
    ) -> RegisteredRouter:
        """Register ``router_tool`` under ``router_id``.

        ``default`` marks the router as the default; the first registered router
        becomes the default when none is marked explicitly.
        """
        if router_id in self._routers:
            raise DuplicateRouterError(f"router '{router_id}' is already registered")
        registry = self.build_registry(router_tool)
        selector = RouterToolSelector(registry)
        cache = RouterContextCache()
        router = RegisteredRouter(
            router_id=router_id,
            tool=router_tool,
            registry=registry,
            selector=selector,
            detector=RouterIntentDetector(selector),
            executor=RouterToolExecutor(registry),
            cache=cache,
            snapshot_service=RouterSnapshotService(cache),
        )
        self._routers[router_id] = router
        if default or self._default_id is None:
            self._default_id = router_id
        return router

    def list(self) -> list[str]:
        """Return the ids of all registered routers."""
        return list(self._routers)

    def invalidate(self) -> None:
        """Clear the tool-result + snapshot caches of every registered router.

        Called after the active connection changes (IP change or re-onboarding)
        so cached Router Tool executions never reference the previous router.
        """
        for registered in self._routers.values():
            registered.cache.clear()
            registered.snapshot_service.clear()

    def resolve(self, router_id: str) -> RegisteredRouter:
        """Return the registered router for ``router_id``.

        Raises :class:`UnknownRouterError` when the id is not registered.
        """
        try:
            return self._routers[router_id]
        except KeyError as exc:
            raise UnknownRouterError(f"unknown router: {router_id}") from exc

    @property
    def default(self) -> RegisteredRouter:
        """Return the default registered router.

        Raises :class:`UnknownRouterError` when no router is registered.
        """
        if self._default_id is None:
            raise UnknownRouterError("no router is registered")
        return self._routers[self._default_id]
