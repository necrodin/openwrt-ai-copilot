"use client";

import { FolderTree } from "lucide-react";

import type { StorageInfo, StorageMountRow } from "@/lib/router-management";
import { formatBytes } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";
import { Gauge } from "@/components/dashboard/gauge";
import {
  isReadonlyFirmwareMount,
  mountUsageTone,
  usableMounts,
} from "@/lib/storage-utils";

type Props = {
  storage: StorageInfo | null;
};

function FilesystemBadge({ mount }: { mount: StorageMountRow }) {
  if (isReadonlyFirmwareMount(mount)) {
    return (
      <Badge variant="outline" className="border-amber-500/40 text-amber-700 dark:text-amber-400">
        read-only firmware
      </Badge>
    );
  }
  if (mount.rootfs || mount.overlay) {
    return (
      <Badge variant="outline" className="border-sky-500/40 text-sky-700 dark:text-sky-400">
        {mount.rootfs ? "rootfs" : "overlay"}
      </Badge>
    );
  }
  return null;
}

/**
 * Filesystem usage by mountpoint: capacity, usage gauge, filesystem type, and
 * mount options as reported by the router. Read-only firmware images (e.g.
 * squashfs ``/rom``) are labelled as such and never shown as capacity
 * exhaustion, and ``df`` header artifacts are never rendered.
 */
export function StorageMounts({ storage }: Props) {
  const mounts = usableMounts(storage?.mounts ?? []);

  return (
    <Widget
      title="Filesystems"
      icon={FolderTree}
      subtitle={
        storage
          ? `${mounts.length} mountpoint${mounts.length === 1 ? "" : "s"}`
          : "Storage inventory loading…"
      }
    >
      {mounts.length === 0 ? (
        <EmptyState message="No mounted filesystems were reported by the router." />
      ) : (
        <div className="space-y-3">
          {mounts.map((mount) => {
            const percent = mount.use_percent;
            return (
              <div key={`${mount.device}:${mount.mountpoint}`} className="rounded-md border px-3 py-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex min-w-0 items-center gap-2">
                    <span className="truncate font-mono text-xs font-medium">
                      {mount.mountpoint}
                    </span>
                    <FilesystemBadge mount={mount} />
                  </div>
                  <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                    {formatBytes(mount.used_bytes)} / {formatBytes(mount.total_bytes)}
                    {percent !== null ? ` · ${percent}%` : ""}
                  </span>
                </div>
                <div className="mt-2">
                  <Gauge value={percent ?? 0} tone={mountUsageTone(percent, mount)} />
                </div>
                <p className="mt-2 truncate text-xs text-muted-foreground">
                  {mount.device}
                  {mount.filesystem ? ` · ${mount.filesystem}` : ""}
                  {mount.options ? ` · ${mount.options}` : ""}
                </p>
              </div>
            );
          })}
        </div>
      )}
    </Widget>
  );
}