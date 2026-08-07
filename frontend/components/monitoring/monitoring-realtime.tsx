"use client";

import { Activity, Cpu, MemoryStick, RefreshCw } from "lucide-react";

import type { RefreshInterval } from "@/hooks/use-monitoring";
import { Card, CardContent } from "@/components/ui/card";
import { formatBitRate, formatBytes } from "@/lib/dashboard-utils";

type ChartProps = {
  data: number[];
  max: number;
  colorClass: string;
};

function Chart({ data, max, colorClass }: ChartProps) {
  const width = 320;
  const height = 64;
  const safeMax = max > 0 ? max : 1;

  if (data.length < 2) {
    return (
      <svg
        viewBox={`0 0 ${width} ${height}`}
        preserveAspectRatio="none"
        className="h-16 w-full"
        aria-hidden
      >
        <line
          x1="0"
          y1={height - 2}
          x2={width}
          y2={height - 2}
          stroke="currentColor"
          strokeOpacity="0.15"
          strokeWidth="1"
        />
      </svg>
    );
  }

  const points = data
    .map((value, index) => {
      const x = (index / (data.length - 1)) * width;
      const y = height - Math.max(0, Math.min(1, value / safeMax)) * (height - 4) - 2;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");

  const area = `0,${height} ${points} ${width},${height}`;

  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      preserveAspectRatio="none"
      className="h-16 w-full"
      aria-hidden
    >
      <polygon points={area} fill="currentColor" className={`opacity-10 ${colorClass}`} />
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        vectorEffect="non-scaling-stroke"
        strokeLinejoin="round"
        strokeLinecap="round"
        className={colorClass}
      />
    </svg>
  );
}

type Props = {
  cpu: number[];
  mem: number[];
  rx: number[];
  tx: number[];
  cpuPercent: number | null;
  memPercent: number | null;
  load: string | null;
  interval: RefreshInterval;
  onIntervalChange: (interval: RefreshInterval) => void;
};

const INTERVALS: Array<{ value: RefreshInterval; label: string }> = [
  { value: 1000, label: "1s" },
  { value: 3000, label: "3s" },
  { value: 5000, label: "5s" },
  { value: 10000, label: "10s" },
  { value: 15000, label: "15s" },
];

export function MonitoringRealtime({
  cpu,
  mem,
  rx,
  tx,
  cpuPercent,
  memPercent,
  load,
  interval,
  onIntervalChange,
}: Props) {
  const currentRx = rx.at(-1) ?? 0;
  const currentTx = tx.at(-1) ?? 0;
  const networkMax = Math.max(currentRx, currentTx) * 1.2 || 1;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-sm font-semibold">Realtime graphs</h3>
        <div className="flex items-center gap-2">
          <RefreshCw className="h-4 w-4 text-muted-foreground" aria-hidden />
          <span className="text-xs text-muted-foreground">Refresh</span>
          <div className="flex overflow-hidden rounded-md border" role="group" aria-label="Refresh interval">
            {INTERVALS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => onIntervalChange(option.value)}
                aria-pressed={interval === option.value}
                className={`px-2.5 py-1 text-xs font-medium transition-colors ${
                  interval === option.value
                    ? "bg-primary text-primary-foreground"
                    : "bg-background text-muted-foreground hover:bg-muted"
                }`}
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <Card>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2">
              <Cpu className="h-4 w-4 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">CPU</p>
              {load ? <span className="text-xs text-muted-foreground">{load}</span> : null}
            </div>
            <p className="text-2xl font-semibold tabular-nums">
              {cpuPercent != null ? `${cpuPercent.toFixed(1)}%` : "—"}
            </p>
            <Chart data={cpu} max={100} colorClass="text-emerald-500" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2">
              <MemoryStick className="h-4 w-4 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">Memory</p>
            </div>
            <p className="text-2xl font-semibold tabular-nums">
              {memPercent != null ? `${memPercent.toFixed(1)}%` : "—"}
            </p>
            <Chart data={mem} max={100} colorClass="text-sky-500" />
          </CardContent>
        </Card>

        <Card>
          <CardContent className="space-y-2">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-muted-foreground" aria-hidden />
              <p className="text-sm font-medium">Network throughput</p>
            </div>
            <p className="text-2xl font-semibold tabular-nums">
              {formatBitRate(currentRx)}
              <span className="text-xs font-normal text-muted-foreground"> ↓ </span>
              {formatBitRate(currentTx)}
              <span className="text-xs font-normal text-muted-foreground"> ↑</span>
            </p>
            <p className="text-xs text-muted-foreground">
              {formatBytes(currentRx / 8)} down · {formatBytes(currentTx / 8)} up this sample
            </p>
            <Chart data={rx} max={networkMax} colorClass="text-emerald-500" />
            <Chart data={tx} max={networkMax} colorClass="text-sky-500" />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}