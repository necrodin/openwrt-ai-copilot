import { HardDrive } from "lucide-react";

import type { StorageMount } from "@/lib/dashboard";
import { formatBytes } from "@/lib/dashboard-utils";
import { Gauge } from "@/components/dashboard/gauge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = { storage: StorageMount[] };

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

export function StorageWidget({ storage }: Props) {
  if (storage.length === 0) {
    return (
      <Widget title="Storage" icon={HardDrive}>
        <EmptyState message="No storage data available." />
      </Widget>
    );
  }

  return (
    <Widget title="Storage" icon={HardDrive} subtitle={`${storage.length} mounts`}>
      <ul className="space-y-3">
        {storage.map((mount) => {
          const percent = mount.use_percent ?? null;
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
            </li>
          );
        })}
      </ul>
    </Widget>
  );
}
