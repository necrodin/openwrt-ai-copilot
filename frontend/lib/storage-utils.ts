import type { StorageMountRow } from "@/lib/router-management";

//: Read-only firmware image filesystems (e.g. ``/rom`` on OpenWrt). Their
//: capacity is fixed and full usage is normal — never writable-space exhaustion.
export const READONLY_FIRMWARE_FILESYSTEMS = new Set([
  "squashfs",
  "erofs",
  "romfs",
]);

/** True for the read-only firmware image mount (e.g. ``/rom`` squashfs). */
export function isReadonlyFirmwareMount(mount: StorageMountRow): boolean {
  return READONLY_FIRMWARE_FILESYSTEMS.has(
    (mount.filesystem || "").toLowerCase(),
  );
}

/**
 * A mount row that is not real data: the ``df`` header line ("Filesystem …
 * Mounted on") can leak into the response and must never be rendered.
 */
export function isBogusMount(mount: StorageMountRow): boolean {
  return mount.device === "Filesystem" || mount.mountpoint === "Mounted on";
}

/** Real mounts, with any ``df`` header artifacts removed. */
export function usableMounts(mounts: StorageMountRow[]): StorageMountRow[] {
  return mounts.filter((mount) => !isBogusMount(mount));
}

export type UsageTone = "good" | "warn" | "danger" | "neutral";

/**
 * Gauge tone for a mount. A read-only firmware image is always neutral —
 * reporting a squashfs ``/rom`` at 100% as "danger" would falsely signal
 * writable capacity exhaustion. Writable mounts use the normal thresholds.
 */
export function mountUsageTone(
  percent: number | null,
  mount: StorageMountRow,
): UsageTone {
  if (isReadonlyFirmwareMount(mount)) {
    return "neutral";
  }
  if (percent === null) {
    return "neutral";
  }
  if (percent >= 90) {
    return "danger";
  }
  if (percent >= 75) {
    return "warn";
  }
  return "good";
}
