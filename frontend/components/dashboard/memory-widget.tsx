import { MemoryStick } from "lucide-react";

import type { MemoryInfo } from "@/lib/dashboard";
import { formatBytes } from "@/lib/dashboard-utils";
import { Gauge } from "@/components/dashboard/gauge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = { memory: MemoryInfo | null };

function tone(percent: number) {
  if (percent >= 90) {
    return "danger" as const;
  }
  if (percent >= 75) {
    return "warn" as const;
  }
  return "good" as const;
}

export function MemoryWidget({ memory }: Props) {
  if (memory === null) {
    return (
      <Widget title="RAM" icon={MemoryStick}>
        <EmptyState message="No memory data available." />
      </Widget>
    );
  }

  const percent = (memory.used_kb / memory.total_kb) * 100;

  return (
    <Widget
      title="RAM"
      icon={MemoryStick}
      subtitle={`${formatBytes(memory.total_kb * 1024)} total`}
    >
      <div className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-3xl font-semibold tabular-nums">
            {formatBytes(memory.used_kb * 1024)}
          </span>
          <span className="text-xs text-muted-foreground">
            {Math.round(percent)}% used
          </span>
        </div>
        <Gauge value={percent} tone={tone(percent)} />
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Available</dt>
            <dd className="tabular-nums">
              {formatBytes((memory.available_kb ?? memory.free_kb) * 1024)}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Free</dt>
            <dd className="tabular-nums">{formatBytes(memory.free_kb * 1024)}</dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Cached</dt>
            <dd className="tabular-nums">
              {formatBytes((memory.cached_kb ?? 0) * 1024)}
            </dd>
          </div>
          <div className="flex justify-between">
            <dt className="text-muted-foreground">Buffered</dt>
            <dd className="tabular-nums">{formatBytes(memory.buffered_kb * 1024)}</dd>
          </div>
        </dl>
      </div>
    </Widget>
  );
}
