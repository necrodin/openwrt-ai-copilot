"""Memory collector.

Sources: ``/proc/meminfo`` (detailed) with ``ubus call system info`` as a
fallback. Values are normalized to kilobytes.
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import MemoryInfo


def _parse_meminfo(text: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for line in text.splitlines():
        key, _, rest = line.partition(":")
        rest = rest.strip().split()[0]
        if rest.isdigit():
            result[key] = int(rest)
    return result


class MemoryCollector(Collector):
    name = "memory"

    def collect(self, ctx: CollectorContext) -> MemoryInfo:
        meminfo = _parse_meminfo(ctx.sh("cat /proc/meminfo", default=""))
        if meminfo:
            total = meminfo.get("MemTotal", 0)
            free = meminfo.get("MemFree", 0)
            buffered = meminfo.get("Buffers", 0)
            cached = meminfo.get("Cached", 0)
            available = meminfo.get("MemAvailable")
            return MemoryInfo(
                total_kb=total,
                free_kb=free,
                used_kb=max(0, total - available) if available else max(0, total - free),
                buffered_kb=buffered,
                cached_kb=cached,
                available_kb=available,
            )

        info = {}
        with suppress(Exception):  # noqa: BLE001 - nothing else to fall back to
            info = ctx.ubus.call("system", "info")
        memory = info.get("memory") or {}
        total = int(memory.get("total", 0))
        free = int(memory.get("free", 0))
        buffered = int(memory.get("buffered", 0))
        return MemoryInfo(
            total_kb=total,
            free_kb=free,
            used_kb=max(0, total - free),
            buffered_kb=buffered,
        )
