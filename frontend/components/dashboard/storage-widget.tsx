import { HardDrive } from "lucide-react";

import type { StorageMount } from "@/lib/dashboard";
import { formatBytes } from "@/lib/dashboard-utils";
import { cn } from "@/lib/utils";
import { Gauge } from "@/components/dashboard/gauge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  storage: StorageMount[];
  loading?: boolean;
  error?: string | null;
};

function tone(percent: number | null) {
  if (percent === null) {
    return "neutral" as const;
  }
  if (percent >= 90) {
    return "danger" as const;
  }
  if (percent >= 75) {
    return "warn" as const;
  }
  return "good" as const;
}

function healthTone(health: string | null): string {
  if (health === "ok") {
    return "bg-emerald-500 text-white";
  }
  if (health === "degraded") {
    return "bg-amber-500 text-white";
  }
  return "bg-muted text-muted-foreground";
}

export function StorageWidget({ storage, loading = false, error = null }: Props) {
  if (storage.length === 0) {
    return (
      <Widget title="Storage" icon={HardDrive} loading={loading} error={error}>
        <EmptyState message="No storage data available." />
      </Widget>
    );
  }

  return (
    <Widget
      title="Storage"
      icon={HardDrive}
      subtitle={`${storage.length} mounts`}
      loading={loading}
      error={error}
    >
      <ul className="space-y-3">
        {storage.map((mount) => {
          const percent = mount.use_percent ?? null;
          const inodePercent = mount.inode_use_percent ?? null;
          return (
            <li key={mount.mountpoint} className="space-y-1">
              <div className="flex items-baseline justify-between gap-2">
                <span className="truncate font-medium">{mount.mountpoint}</span>
                <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                  {formatBytes(mount.used_bytes)} / {formatBytes(mount.total_bytes)}
                </span>
              </div>
              <Gauge value={percent ?? 0} tone={tone(percent)} />
              <p className="text-xs text-muted-foreground">
                {mount.device}
                {mount.filesystem ? ` · ${mount.filesystem}` : ""}
                {percent !== null ? ` · ${percent.toFixed(1)}%` : ""}
              </p>
              {(inodePercent !== null || mount.wear != null || mount.health != null) ? (
                <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                  {inodePercent !== null ? (
                    <span>{`inodes ${inodePercent.toFixed(1)}%`}</span>
                  ) : null}
                  {mount.wear != null ? <span>{`wear ${mount.wear}`}</span> : null}
                  {mount.health != null ? (
                    <span
                      className={cn(
                        "rounded px-1.5 py-0.5 text-[11px] font-semibold",
                        healthTone(mount.health),
                      )}
                    >
                      {mount.health}
                    </span>
                  ) : null}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Widget>
  );
}
