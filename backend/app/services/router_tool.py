"""Provider-independent Router Tool layer.

A thin, read-only facade over the latest router snapshot produced by the Router
Agent. It exposes structured getters (system, CPU, memory, storage, network) and
never runs shell commands — all OpenWrt-specific collection stays inside
``router-agent``. Structured extraction is reused from ``router_context`` so the
tool and the chat context never drift apart.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.schemas.dashboard import DashboardUpdate
from app.services.router_context import build_context


class RouterTool:
    """Read-only access to the router's current state.

    Args:
        latest: callable returning the latest :class:`DashboardUpdate` (or
            ``None`` when no snapshot has been collected yet). Each getter
            rebuilds from the freshest snapshot available.
    """

    def __init__(self, latest: Callable[[], DashboardUpdate | None]) -> None:
        self._latest = latest

    def _context(self) -> dict[str, Any]:
        return build_context(self._latest())

    @property
    def available(self) -> bool:
        """True when a router snapshot is available."""
        return bool(self._context().get("available"))

    def get_system_info(self) -> dict[str, Any]:
        """Router identity: hostname, model, board, firmware, kernel, uptime."""
        return dict(self._context().get("router_info") or {})

    def get_cpu_info(self) -> dict[str, Any]:
        """CPU/load summary: usage percent, cores, load 1/5/15."""
        return dict(self._context().get("system_load") or {})

    def get_memory_info(self) -> dict[str, Any]:
        """Memory summary in KB with a used-percent figure."""
        return dict(self._context().get("memory_summary") or {})

    def get_storage_info(self) -> list[dict[str, Any]]:
        """Per-mount storage usage (mountpoint, filesystem, GB, percent)."""
        return list(self._context().get("storage_summary") or [])

    def get_network_info(self) -> list[dict[str, Any]]:
        """Per-interface network summary (name, status, proto, IP, traffic)."""
        return list(self._context().get("network_summary") or [])

    def get_wifi_info(self) -> dict[str, Any]:
        """Wireless summary: detected radios and total associated stations."""
        return dict(self._context().get("wifi_summary") or {})
