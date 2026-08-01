"""Storage collector.

Runs ``df -kP`` and normalizes each mount. Values are converted from kibibytes
to bytes.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import StorageMount

_KB = 1024


def _parse_df(text: str) -> list[StorageMount]:
    mounts: list[StorageMount] = []
    for line in text.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 6 or not parts[1].isdigit():
            continue
        device, kb_total, kb_used, kb_avail, use_pct, mountpoint = parts[:6]
        if mountpoint.startswith("/") is False:
            # mountpoint containing spaces pushes columns right
            mountpoint = " ".join(parts[5:])
        try:
            pct = float(use_pct.rstrip("%"))
        except ValueError:
            pct = None
        mounts.append(
            StorageMount(
                device=device,
                mountpoint=mountpoint,
                filesystem="",
                total_bytes=int(kb_total) * _KB,
                used_bytes=int(kb_used) * _KB,
                available_bytes=int(kb_avail) * _KB,
                use_percent=pct,
            )
        )
    return mounts


class StorageCollector(Collector):
    name = "storage"

    def collect(self, ctx: CollectorContext) -> list[StorageMount]:
        return _parse_df(ctx.sh("df -kP", default=""))
