"""Router snapshot: unified, immutable view of the current router state.

Combines existing Router Tool results into one object that exposes structured
sections (system, cpu, memory, storage, network, wifi). Missing sections are
represented as ``None``. Collection reuses :class:`RouterContextCache` so no
tool is executed twice and successful results are reused across requests.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.router_context_cache import RouterContextCache
from app.services.router_tool_executor import RouterToolExecutor, RouterToolResult

_SECTION_NAMES = ("system", "cpu", "memory", "storage", "network", "wifi")


@dataclass(frozen=True)
class RouterSnapshot:
    """Immutable snapshot of the router's current state.

    Each section holds the structured data of the matching Router Tool result,
    or ``None`` when the section is unavailable.
    """

    system: dict[str, Any] | None = None
    cpu: dict[str, Any] | None = None
    memory: dict[str, Any] | None = None
    storage: list[dict[str, Any]] | None = None
    network: list[dict[str, Any]] | None = None
    wifi: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize the snapshot to a plain dict (null for missing sections)."""
        return {
            "system": self.system,
            "cpu": self.cpu,
            "memory": self.memory,
            "storage": self.storage,
            "network": self.network,
            "wifi": self.wifi,
        }


class RouterSnapshotService:
    """Builds :class:`RouterSnapshot` objects from Router Tool results.

    The service consults the per-session :class:`RouterContextCache` first and
    only executes tools that are not already cached, so each tool runs at most
    once and successful results are reused.
    """

    def __init__(self, cache: RouterContextCache | None = None) -> None:
        self._cache = cache if cache is not None else RouterContextCache()

    def clear(self) -> None:
        """Drop every cached tool result so the next build re-executes tools."""
        self._cache.clear()

    def build(
        self,
        executor: RouterToolExecutor,
        session_id: str | None,
        requests: list[str],
    ) -> RouterSnapshot:
        """Build a snapshot covering ``requests`` for ``session_id``.

        Unavailable or failed sections are set to ``None``.
        """
        sid = session_id or ""
        collected: dict[str, RouterToolResult] = {}
        pending: list[str] = []
        for name in requests:
            cached = self._cache.get(sid, name)
            if cached is not None:
                collected[name] = cached
            else:
                pending.append(name)
        if pending:
            for result in executor.execute(pending):
                self._cache.set(sid, result.name, result)
                collected[result.name] = result
        return RouterSnapshot(
            system=_value(collected.get("system")),
            cpu=_value(collected.get("cpu")),
            memory=_value(collected.get("memory")),
            storage=_value(collected.get("storage")),
            network=_value(collected.get("network")),
            wifi=_value(collected.get("wifi")),
        )

    def render_markdown(
        self,
        snapshot: RouterSnapshot,
        intents: list[str] | None = None,
    ) -> str | None:
        """Render ``snapshot`` as structured markdown (may be ``None``).

        ``intents`` limits the rendered sections to the requested tool intents;
        when omitted all sections are rendered.
        """
        system = snapshot.system or {}
        cpu = snapshot.cpu or {}
        memory = snapshot.memory or {}
        storage = snapshot.storage or []
        network = snapshot.network or []
        wifi = snapshot.wifi or {}
        if not (system or cpu or memory or storage or network or wifi):
            return None
        selected = set(intents) if intents else set(_SECTION_NAMES)

        lines: list[str] = []
        if "system" in selected and system:
            lines += [
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

        if "cpu" in selected and cpu:
            lines.append("## CPU")
            usage = cpu.get("usage_percent")
            usage_text = f"{usage:.1f}%" if isinstance(usage, (int, float)) else "N/A"
            lines.append(f"- Usage: {usage_text} ({cpu.get('cores', 0)} cores)")
            lines.append(
                "- Load: "
                f"{cpu.get('load_1', 0):.2f} / {cpu.get('load_5', 0):.2f} / "
                f"{cpu.get('load_15', 0):.2f}"
            )
            lines.append("")

        if "memory" in selected and memory:
            lines.append("## Memory")
            used = memory.get("used_kb")
            total = memory.get("total_kb")
            lines.append(
                f"- RAM: {_format_kb(used)} / {_format_kb(total)} "
                f"({memory.get('used_percent', 0):.1f}%)"
            )
            lines.append("")

        if "storage" in selected and storage:
            lines.append("## Storage")
            for mount in storage:
                used_gb = f"{mount.get('used_gb') or 0:.1f}G"
                total_gb = f"{mount.get('total_gb') or 0:.1f}G"
                lines.append(
                    f"- {mount.get('mountpoint', '?')} ({mount.get('filesystem', '?')}): "
                    f"{used_gb} / {total_gb} ({mount.get('use_percent') or 0:.1f}%)"
                )
            lines.append("")

        if "network" in selected and network:
            lines.append("## Network Interfaces")
            for iface in network:
                status = "UP" if iface.get("up") else "DOWN"
                ip = iface.get("ipv4") or iface.get("mac") or "—"
                lines.append(
                    f"- **{iface.get('name', '?')}** ({status}) — {ip} — "
                    f"proto: {iface.get('proto') or '—'}"
                )

        if "wifi" in selected and wifi:
            lines.append("## Wireless")
            client_count = wifi.get("client_count") or 0
            lines.append(f"- Associated stations: {client_count}")
            for radio in wifi.get("radios") or []:
                band = radio.get("band") or "?"
                ssid = radio.get("ssid") or "?"
                stations = radio.get("station_count") or 0
                lines.append(
                    f"- **{radio.get('name', '?')}** ({band}) — SSID {ssid} · "
                    f"{stations} station{'' if stations == 1 else 's'}"
                )

        return "\n".join(lines)


def _value(result: RouterToolResult | None) -> Any:
    """Return the result value for a successful result, else ``None``."""
    if result is not None and result.ok:
        return result.result
    return None


def _format_kb(kb: int | None) -> str:
    if kb is None:
        return "unknown"
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"
