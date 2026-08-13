"""Structured AI context generation from router snapshots.

Produces a markdown/text summary of all router state that is suitable as input
to the AI chat pipeline. This runs on-demand via the router context API endpoint
and exposes the same data the system prompt already embeds — but in a format the
frontend can pre-fetch or display independently of chat.
"""

from __future__ import annotations

from app.schemas.dashboard import DashboardUpdate


def _format_bytes(kb: int | None) -> str:
    if kb is None:
        return "unknown"
    if kb >= 1024 * 1024:
        return f"{kb / (1024 * 1024):.1f} GB"
    if kb >= 1024:
        return f"{kb / 1024:.1f} MB"
    return f"{kb} KB"


def _format_uptime(seconds: float | None) -> str:
    if seconds is None:
        return "unknown"
    days = int(seconds // 86400)
    hours = int((seconds % 86400) // 3600)
    minutes = int((seconds % 3600) // 60)
    parts = []
    if days:
        parts.append(f"{days}d")
    if hours:
        parts.append(f"{hours}h")
    parts.append(f"{minutes}m")
    return " ".join(parts)


def build_context(update: DashboardUpdate | None) -> dict:
    """Return structured AI context from the latest router snapshot.

    The returned dict contains:
    - ``router_info``: identity (hostname, model, firmware, kernel, arch, uptime)
    - ``system_health``: CPU load, memory usage, temperature
    - ``storage_summary``: mountpoints with usage
    - ``network_summary``: interfaces with IPs, status, traffic
    - ``wifi_summary``: radios and connected clients
    - ``markdown``: pre-rendered markdown string for direct injection
    - ``raw_snapshot``: the full DeviceSnapshot dict (for use by chat_service)
    """
    if update is None or update.snapshot is None:
        return {
            "available": False,
            "reason": "No snapshot data available",
            "router_info": None,
            "network_health": None,
            "memory_summary": None,
            "storage_summary": None,
            "network_summary": None,
            "wifi_summary": None,
            "markdown": "No router data is currently available.",
            "raw_snapshot": None,
        }

    snap = update.snapshot
    kernel = snap.kernel

    # --- router identity ---
    router_info = {
        "hostname": kernel.hostname if kernel else snap.meta.host or "unknown",
        "model": kernel.model if kernel else snap.meta.model or "unknown",
        "board": kernel.board if kernel else snap.meta.board or "unknown",
        # ``kernel.version`` is empty on modern OpenWrt (the release is in
        # ``meta.firmware``/``kernel.release``), so fall back when it is blank.
        "firmware": (
            (kernel.version if kernel else None) or snap.meta.firmware or "unknown"
        ),
        "kernel": kernel.kernel if kernel else "unknown",
        "architecture": kernel.architecture if kernel else "unknown",
        "uptime_seconds": float(snap.cpu.uptime_seconds) if snap.cpu else None,
        "uptime": _format_uptime(float(snap.cpu.uptime_seconds)) if snap.cpu else "unknown",
    }

    # -- CPU + load --
    cpu_data = snap.cpu
    load_parts = {
        "usage_percent": cpu_data.usage_percent if cpu_data else None,
        "cores": cpu_data.cores if cpu_data else 0,
        "load_1": cpu_data.load_1 if cpu_data else 0,
        "load_5": cpu_data.load_5 if cpu_data else 0,
        "load_15": cpu_data.load_15 if cpu_data else 0,
    }

    # -- Memory --
    mem_data = snap.memory
    memory_summary = {}
    if mem_data:
        memory_summary = {
            "total_kb": mem_data.total_kb,
            "used_kb": mem_data.used_kb,
            "free_kb": mem_data.free_kb,
            "available_kb": mem_data.available_kb,
            "cached_kb": mem_data.cached_kb,
            "buffered_kb": mem_data.buffered_kb,
            "used_percent": (
                round(mem_data.used_kb / mem_data.total_kb * 100, 1) if mem_data.total_kb else 0
            ),
        }

    # -- Storage mounts --
    storage_summary = [
        {
            "mountpoint": m.mountpoint,
            "device": m.device,
            "filesystem": m.filesystem,
            "total_gb": m.total_bytes / (1024**3) if m.total_bytes else None,
            "used_gb": m.used_bytes / (1024**3) if m.used_bytes else None,
            "use_percent": m.use_percent,
        }
        for m in snap.storage
    ]

    # -- Network interfaces --
    network_summary = []
    for iface in snap.network:
        ipv4 = next((a.address for a in iface.addresses if a.family == "ipv4"), None)
        network_summary.append(
            {
                "name": iface.name,
                "up": iface.up,
                "proto": iface.proto,
                "mac": iface.mac,
                "ipv4": ipv4,
                "rx_bytes": iface.rx_bytes,
                "tx_bytes": iface.tx_bytes,
            }
        )

    # -- WiFi --
    wifi_summary = {
        "radios": [
            {
                "name": r.name,
                "up": r.up,
                "ssid": r.ssid,
                "band": r.band,
                "channel": r.channel,
                "clients": r.station_count,
            }
            for r in snap.wifi.radios
        ],
        "client_count": sum(r.station_count for r in snap.wifi.radios),
    }

    # Render markdown
    lines = [
        f"## Router: {router_info['hostname']}",
        f"- **Model**: {router_info['model']} ({router_info['board']})",
        f"- **Firmware**: {router_info['firmware']}",
        f"- **Kernel**: {router_info['kernel']} ({router_info['architecture']})",
        f"- **Uptime**: {router_info['uptime']}",
        "",
    ]
    if load_parts and load_parts.get("cores", 0) > 0:
        lines.append("## System Health")
        usage = (
            f"{load_parts['usage_percent']:.1f}% used"
            if load_parts["usage_percent"] is not None
            else "N/A"
        )
        lines.append(f"- CPU: {usage} ({load_parts['cores']} cores)")
        load_1 = load_parts.get("load_1") or 0
        load_5 = load_parts.get("load_5") or 0
        load_15 = load_parts.get("load_15") or 0
        lines.append(f"- Load: {load_1:.2f} / {load_5:.2f} / {load_15:.2f}")
        if memory_summary:
            lines.append(
                f"- RAM: {_format_bytes(memory_summary['used_kb'])} / "
                f"{_format_bytes(memory_summary['total_kb'])} "
                f"({memory_summary['used_percent']}%)"
            )
        lines.append("")
    if storage_summary:
        lines.append("## Storage")
        for s in storage_summary:
            used = f"{s['used_gb']:.1f}" if s["used_gb"] else "?"
            total = f"{s['total_gb']:.1f}" if s["total_gb"] else "?"
            lines.append(
                f"- {s['mountpoint']} ({s['filesystem']}): "
                f"{used}G / {total}G ({s['use_percent']:.1f}%)"
            )
        lines.append("")
    if network_summary:
        lines.append("## Network Interfaces")
        for n in network_summary:
            status = "UP" if n["up"] else "DOWN"
            ip = n.get("ipv4") or "—"
            lines.append(f"- **{n['name']}** ({status}) — {ip} — proto: {n.get('proto', '—')}")
        lines.append("")
    if wifi_summary.get("radios"):
        lines.append("## WiFi")
        for r in wifi_summary["radios"]:
            lines.append(
                f"- **{r['name']}** ({r.get('ssid', '—')}) — "
                f"{r.get('band', '—')} ch{r.get('channel', '?')} — "
                f"{r.get('clients', 0)} clients"
            )

    markdown = "\n".join(lines)

    return {
        "available": True,
        "collected_at": snap.meta.collected_at.isoformat(),
        "router_info": router_info,
        "system_load": load_parts,
        "memory_summary": memory_summary,
        "storage_summary": storage_summary,
        "network_summary": network_summary,
        "wifi_summary": wifi_summary,
        "markdown": markdown,
        "raw_snapshot": snap.model_dump(mode="json") if snap else None,
    }
