"use client";

import { Activity } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { DeviceSnapshot } from "@/lib/dashboard";
import { formatBitRate, formatBytes } from "@/lib/dashboard-utils";
import { Sparkline } from "@/components/dashboard/sparkline";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = { snapshot: DeviceSnapshot | null };

const HISTORY_LIMIT = 60;

function totalTraffic(snapshot: DeviceSnapshot): { rx: number; tx: number } {
  return snapshot.network.reduce(
    (acc, iface) => ({
      rx: acc.rx + (iface.rx_bytes ?? 0),
      tx: acc.tx + (iface.tx_bytes ?? 0),
    }),
    { rx: 0, tx: 0 },
  );
}

export function BandwidthWidget({ snapshot }: Props) {
  const [rates, setRates] = useState<{ rx: number; tx: number }>({ rx: 0, tx: 0 });
  const [history, setHistory] = useState<{ rx: number[]; tx: number[] }>({
    rx: [],
    tx: [],
  });
  const previous = useRef<{ time: number; rx: number; tx: number } | null>(null);

  useEffect(() => {
    if (snapshot === null) {
      return;
    }
    const traffic = totalTraffic(snapshot);
    const now = Date.now();
    const prev = previous.current;
    previous.current = { time: now, ...traffic };
    if (prev === null) {
      return;
    }
    const elapsed = (now - prev.time) / 1000;
    if (elapsed <= 0) {
      return;
    }
    const rxRate = Math.max(0, (traffic.rx - prev.rx) / elapsed) * 8;
    const txRate = Math.max(0, (traffic.tx - prev.tx) / elapsed) * 8;
    setRates({ rx: rxRate, tx: txRate });
    setHistory((current) => ({
      rx: [...current.rx.slice(-(HISTORY_LIMIT - 1)), rxRate],
      tx: [...current.tx.slice(-(HISTORY_LIMIT - 1)), txRate],
    }));
  }, [snapshot]);

  if (snapshot === null || snapshot.network.length === 0) {
    return (
      <Widget title="Bandwidth" icon={Activity}>
        <EmptyState message="Waiting for traffic data." />
      </Widget>
    );
  }

  return (
    <Widget title="Bandwidth" icon={Activity} subtitle="Live throughput (last 60 samples)">
      <div className="space-y-4">
        <div className="grid grid-cols-2 gap-3">
          <div className="rounded-md border p-3">
            <p className="text-xs text-muted-foreground">Download</p>
            <p className="text-2xl font-semibold tabular-nums text-emerald-600">
              {formatBitRate(rates.rx)}
            </p>
            <Sparkline data={history.rx} className="mt-2 h-8 w-full text-emerald-500" />
          </div>
          <div className="rounded-md border p-3">
            <p className="text-xs text-muted-foreground">Upload</p>
            <p className="text-2xl font-semibold tabular-nums text-sky-600">
              {formatBitRate(rates.tx)}
            </p>
            <Sparkline data={history.tx} className="mt-2 h-8 w-full text-sky-500" />
          </div>
        </div>
        <ul className="space-y-1 text-sm">
          {snapshot.network.map((iface) => (
            <li
              key={iface.name}
              className="flex items-center justify-between gap-2"
            >
              <span className="truncate">{iface.name}</span>
              <span className="shrink-0 text-xs text-muted-foreground tabular-nums">
                {formatBytes(iface.rx_bytes)} ↓ · {formatBytes(iface.tx_bytes)} ↑
              </span>
            </li>
          ))}
        </ul>
      </div>
    </Widget>
  );
}
