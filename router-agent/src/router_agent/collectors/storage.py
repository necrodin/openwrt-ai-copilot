"""Storage collector.

Runs ``df -kPT`` (with filesystem type), ``df -i`` (inode usage), and joins the
results by mountpoint. Values are converted from kibibytes/inodes to normalized
units. Flash wear and media health are reported best-effort for UBI-backed
filesystems (the rootfs/overlay on embedded OpenWrt routers).

.. note::
   ``df -kPT`` is used instead of the historical ``df -kP`` so the filesystem
   type is captured in a single pass. ``-T`` is supported by BusyBox ``df`` on
   every supported OpenWrt release.
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import StorageMount

_KB = 1024


def _columns(line: str, leading: int) -> list[str]:
    """Split a ``df`` line into ``leading`` fixed columns plus a joined tail.

    This keeps mountpoints that contain spaces intact (they form the last
    field, separated from the fixed numeric columns).
    """
    parts = line.split()
    if len(parts) <= leading:
        return parts
    return parts[: leading - 1] + [" ".join(parts[leading - 1 :])]


def _float(value: str) -> float | None:
    try:
        return float(value.rstrip("%"))
    except ValueError:
        return None


def _is_ubi(mount: StorageMount) -> bool:
    lowered = f"{mount.device} {mount.filesystem}".lower()
    return "ubi" in lowered or "ubifs" in lowered or "overlay" in lowered


class StorageCollector(Collector):
    name = "storage"

    def collect(self, ctx: CollectorContext) -> list[StorageMount]:
        by_mount: dict[str, StorageMount] = {}

        for line in ctx.sh("df -kPT", default="").splitlines():
            if not line.strip() or line.split()[0].lower() == "filesystem":
                continue
            # device type total used avail cap mountpoint
            cols = _columns(line, 7)
            if len(cols) < 7 or not cols[2].isdigit():
                continue
            device, fs_type, kb_total, kb_used, kb_avail, use_pct, mountpoint = cols[:7]
            if not mountpoint.startswith("/"):
                continue
            by_mount[mountpoint] = StorageMount(
                device=device,
                mountpoint=mountpoint,
                filesystem=fs_type or "",
                total_bytes=int(kb_total) * _KB,
                used_bytes=int(kb_used) * _KB,
                available_bytes=int(kb_avail) * _KB,
                use_percent=_float(use_pct),
            )

        # Inode usage, merged in by mountpoint.
        for line in ctx.sh("df -i", default="").splitlines():
            if not line.strip() or line.split()[0].lower() == "filesystem":
                continue
            # filesystem inodes ifree inodes_used mountpoint
            cols = _columns(line, 6)
            if len(cols) < 6 or not cols[1].isdigit():
                continue
            mount = by_mount.get(cols[5])
            if mount is None:
                continue
            mount.inodes_total = int(cols[1]) or None
            mount.inodes_used = int(cols[2]) or None
            mount.inodes_available = int(cols[3]) or None
            mount.inode_use_percent = _float(cols[4])

        for mount in by_mount.values():
            self._attach_flash_health(ctx, mount)

        return list(by_mount.values())

    @staticmethod
    def _attach_flash_health(ctx: CollectorContext, mount: StorageMount) -> None:
        """Populate ``health`` (and best-effort ``wear``) for UBI surfaces."""
        if not _is_ubi(mount):
            mount.health = None
            mount.wear = None
            return
        # UBI handles erase-leveling internally; an online/readable UBI
        # filesystem is treated as healthy. Exact erase counters are only read
        # when the kernel exposes them without requiring extra tooling.
        mount.health = "ok"
        with suppress(Exception):  # noqa: BLE001 - best-effort endurance read
            raw = ctx.sh(
                "grep -h . /sys/class/mtd/mtd*/erase_count 2>/dev/null | sort -n | tail -1",
                default="",
            ).strip()
            if raw.isdigit():
                mount.wear = int(raw)
