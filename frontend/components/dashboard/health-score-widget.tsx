import { HeartPulse } from "lucide-react";

import type { DeviceSnapshot } from "@/lib/dashboard";
import {
  computeHealthScore,
  type HealthFactorStatus,
  type HealthTone,
} from "@/lib/health-score";
import { cn } from "@/lib/utils";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  snapshot: DeviceSnapshot | null;
  loading?: boolean;
  error?: string | null;
};

const toneMeta: Record<
  HealthTone,
  { label: string; tone: StatusBadgeTone; color: string }
> = {
  excellent: { label: "Excellent", tone: "success", color: "text-emerald-500" },
  good: { label: "Good", tone: "info", color: "text-sky-500" },
  fair: { label: "Fair", tone: "warning", color: "text-amber-500" },
  poor: { label: "Poor", tone: "danger", color: "text-red-500" },
};

const factorDot: Record<HealthFactorStatus, string> = {
  ok: "bg-emerald-500",
  warn: "bg-amber-500",
  bad: "bg-red-500",
};

export function HealthScoreWidget({ snapshot, loading = false, error = null }: Props) {
  const health = computeHealthScore(snapshot);

  return (
    <Widget
      title="Health Score"
      icon={HeartPulse}
      subtitle={health === null ? "No snapshot yet" : "Overall device health"}
      loading={loading}
      error={error}
    >
      {health === null ? (
        <EmptyState message="Waiting for a device snapshot." />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <span className={cn("text-4xl font-bold tabular-nums", toneMeta[health.tone].color)}>
              {health.score}
            </span>
            <StatusBadge label={toneMeta[health.tone].label} tone={toneMeta[health.tone].tone} />
          </div>

          <div className="h-2 w-full overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={health.score} aria-valuemin={0} aria-valuemax={100}>
            <div
              className={cn("h-full rounded-full transition-[width] duration-700", toneMeta[health.tone].color)}
              style={{ width: `${health.score}%` }}
            />
          </div>

          <ul className="space-y-1.5">
            {health.factors.map((factor) => (
              <li key={factor.label} className="flex items-center justify-between gap-3 text-sm">
                <span className="text-muted-foreground">{factor.label}</span>
                <span className="flex items-center gap-2 tabular-nums">
                  <span>{factor.detail}</span>
                  <span className={cn("size-1.5 shrink-0 rounded-full", factorDot[factor.status])} aria-hidden />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </Widget>
  );
}
