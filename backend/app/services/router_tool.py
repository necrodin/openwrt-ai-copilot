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

    # ------------------------------------------------------------------ #
    # Rendering                                                          #
    # ------------------------------------------------------------------ #

    def render_markdown(self) -> str | None:
        """Render the collected tool data as structured markdown.

        Returns ``None`` when no router snapshot is available so callers can
        continue without the router section.
        """
        if not self.available:
            return None
        system = self.get_system_info()
        cpu = self.get_cpu_info()
        memory = self.get_memory_info()
        storage = self.get_storage_info()
        network = self.get_network_info()

        lines = [
            "## Router",
            f"- Hostname: {system.get('hostname', 'unknown')}",
            f"- Model: {system.get('model', 'unknown')} ({system.get('board', 'unknown')})",
            f"- Firmware: {system.get('firmware', 'unknown')}",
            f"- Kernel: {system.get('kernel', 'unknown')} "
            f"({system.get('architecture', 'unknown')})",
        ]
        uptime = system.get("uptime")
        if uptime:
            lines.append(f"- Uptime: {uptime}")
        lines.append("")

        lines.append("## CPU")
        usage = cpu.get("usage_percent")
        usage_text = f"{usage:.1f}%" if isinstance(usage, (int, float)) else "N/A"
        lines.append(f"- Usage: {usage_text} ({cpu.get('cores', 0)} cores)")
        lines.append(
            "- Load: "
            f"{cpu.get('load_1', 0):.2f} / {cpu.get('load_5', 0):.2f} / {cpu.get('load_15', 0):.2f}"
        )
        lines.append("")

        lines.append("## Memory")
        used = memory.get("used_kb")
        total = memory.get("total_kb")
        lines.append(
            f"- RAM: {_format_kb(used)} / {_format_kb(total)} "
            f"({memory.get('used_percent', 0):.1f}%)"
        )
        lines.append("")

        if storage:
            lines.append("## Storage")
            for mount in storage:
                used_gb = f"{mount.get('used_gb') or 0:.1f}G"
                total_gb = f"{mount.get('total_gb') or 0:.1f}G"
                lines.append(
                    f"- {mount.get('mountpoint', '?')} ({mount.get('filesystem', '?')}): "
                    f"{used_gb} / {total_gb} ({mount.get('use_percent') or 0:.1f}%)"
                )
            lines.append("")

        if network:
            lines.append("## Network Interfaces")
            for iface in network:
                status = "UP" if iface.get("up") else "DOWN"
                ip = iface.get("ipv4") or iface.get("mac") or "—"
                lines.append(
                    f"- **{iface.get('name', '?')}** ({status}) — {ip} — "
                    f"proto: {iface.get('proto') or '—'}"
                )

        return "\n".join(lines)


def _format_kb(kb: int | None) -> str:
    if kb is None:
        return "unknown"
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"
