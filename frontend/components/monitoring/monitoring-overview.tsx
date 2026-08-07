"use client";

import type { DeviceSnapshot } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { Gauge } from "@/components/dashboard/gauge";
import { formatBytes, formatDuration } from "@/lib/dashboard-utils";

type Props = {
  snapshot: DeviceSnapshot;
};

function tone(value: number | null, warn = 75, danger = 90): "good" | "warn" | "danger" {
  if (value === null) {
    return "good";
  }
  if (value >= danger) {
    return "danger";
  }
  if (value >= warn) {
    return "warn";
  }
  return "good";
}

function flashMount(snapshot: DeviceSnapshot) {
  const overlay = snapshot.storage.find(
    (mount) =>
      mount.mountpoint === "/overlay" ||
      (mount.device || "").includes("overlay") ||
      (mount.filesystem || "").toLowerCase().includes("ubifs"),
  );
  return (
    overlay ??
    snapshot.storage.find((mount) => mount.mountpoint === "/") ??
    snapshot.storage[0]
  );
}

export function MonitoringOverview({ snapshot }: Props) {
  const cpu = snapshot.cpu;
  const memory = snapshot.memory;
  const flash = flashMount(snapshot);

  const memPercent =
    memory && memory.total_kb > 0 ? (memory.used_kb / memory.total_kb) * 100 : null;
  const swapPercent =
    memory && memory.swap_total_kb ? (memory.swap_used_kb ?? 0) / memory.swap_total_kb * 100 : null;

  const stats: Array<{ label: string; value: string; sub?: string; percent?: number | null }> = [
    {
      label: "CPU usage",
      value: cpu?.usage_percent != null ? `${Math.round(cpu.usage_percent)}%` : "—",
      sub: `${cpu?.cores ?? 1} core${(cpu?.cores ?? 1) === 1 ? "" : "s"}`,
      percent: cpu?.usage_percent ?? null,
    },
    {
      label: "Load average",
      value: cpu ? `${cpu.load_1.toFixed(2)} / ${cpu.load_5.toFixed(2)} / ${cpu.load_15.toFixed(2)}` : "—",
      sub: "1 · 5 · 15 min",
    },
    {
      label: "Memory usage",
      value: memory ? `${formatBytes(memory.used_kb * 1024)} / ${formatBytes(memory.total_kb * 1024)}` : "—",
      sub: memPercent != null ? `${memPercent.toFixed(1)}% used` : undefined,
      percent: memPercent,
    },
    {
      label: "Swap",
      value: memory && memory.swap_total_kb ? `${formatBytes((memory.swap_used_kb ?? 0) * 1024)} / ${formatBytes(memory.swap_total_kb * 1024)}` : "—",
      sub: memory && memory.swap_total_kb && swapPercent != null ? `${swapPercent.toFixed(1)}% used` : "no swap",
      percent: swapPercent,
    },
    {
      label: "Storage",
      value: snapshot.storage.length ? `${formatBytes(snapshot.storage[0].used_bytes)} / ${formatBytes(snapshot.storage[0].total_bytes)}` : "—",
      sub: snapshot.storage.length ? `${snapshot.storage.length} mount${snapshot.storage.length === 1 ? "" : "s"}` : undefined,
    },
    {
      label: "Flash usage",
      value: flash ? `${formatBytes(flash.used_bytes)} / ${formatBytes(flash.total_bytes)}` : "—",
      sub: flash ? `${flash.mountpoint} · ${flash.use_percent?.toFixed(1) ?? "?"}%` : undefined,
      percent: flash?.use_percent ?? null,
    },
    {
      label: "Uptime",
      value: cpu ? formatDuration(cpu.uptime_seconds) : "—",
      sub: cpu ? "since boot" : undefined,
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {stats.map((stat) => (
        <Card key={stat.label}>
          <CardContent className="space-y-2">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              {stat.label}
            </p>
            <p className="truncate text-base font-semibold">{stat.value || "—"}</p>
            {stat.sub ? <p className="truncate text-xs text-muted-foreground">{stat.sub}</p> : null}
            {stat.percent != null ? (
              <Gauge value={stat.percent} tone={tone(stat.percent)} />
            ) : null}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}