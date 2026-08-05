import { Cpu } from "lucide-react";

import type { CpuInfo } from "@/lib/dashboard";
import { formatDuration } from "@/lib/dashboard-utils";
import { Gauge } from "@/components/dashboard/gauge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = { cpu: CpuInfo | null; loading?: boolean; error?: string | null };

function tone(value: number) {
  if (value >= 85) {
    return "danger" as const;
  }
  if (value >= 65) {
    return "warn" as const;
  }
  return "good" as const;
}

export function CpuWidget({ cpu, loading = false, error = null }: Props) {
  if (cpu === null || cpu.usage_percent === null) {
    return (
      <Widget title="CPU" icon={Cpu} loading={loading} error={error}>
        <EmptyState message="No CPU data available." />
      </Widget>
    );
  }

  return (
    <Widget
      title="CPU"
      icon={Cpu}
      subtitle={`${cpu.cores} cores · ${cpu.frequency_mhz ? `${cpu.frequency_mhz} MHz` : "frequency n/a"} · up ${formatDuration(cpu.uptime_seconds)}`}
      loading={loading}
      error={error}
    >
      <div className="space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-3xl font-semibold tabular-nums">
            {Math.round(cpu.usage_percent)}%
          </span>
          <span className="text-xs text-muted-foreground">used</span>
        </div>
        <Gauge value={cpu.usage_percent} tone={tone(cpu.usage_percent)} />
        <div className="grid grid-cols-3 gap-2 text-center">
          <div>
            <p className="text-lg font-medium tabular-nums">{cpu.load_1.toFixed(2)}</p>
            <p className="text-xs text-muted-foreground">1 min</p>
          </div>
          <div>
            <p className="text-lg font-medium tabular-nums">{cpu.load_5.toFixed(2)}</p>
            <p className="text-xs text-muted-foreground">5 min</p>
          </div>
          <div>
            <p className="text-lg font-medium tabular-nums">{cpu.load_15.toFixed(2)}</p>
            <p className="text-xs text-muted-foreground">15 min</p>
          </div>
        </div>
      </div>
    </Widget>
  );
}
