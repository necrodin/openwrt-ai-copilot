"use client";

import { useMemo, useState } from "react";

import type { WirelessStation } from "@/hooks/use-wireless";
import { EmptyState } from "@/components/dashboard/widget";
import { formatBitRate, formatDuration } from "@/lib/dashboard-utils";

type Props = {
  stations: WirelessStation[];
};

type SortKey = "signal" | "hostname" | "rate" | "time";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "signal", label: "Signal" },
  { value: "hostname", label: "Hostname" },
  { value: "rate", label: "Rate" },
  { value: "time", label: "Connected" },
];

function signalTone(signal: number | null): string {
  if (signal === null) {
    return "text-muted-foreground";
  }
  if (signal >= -60) {
    return "text-emerald-600 dark:text-emerald-400";
  }
  if (signal >= -75) {
    return "text-amber-600 dark:text-amber-400";
  }
  return "text-red-600 dark:text-red-400";
}

export function WirelessStations({ stations }: Props) {
  const [sortKey, setSortKey] = useState<SortKey>("signal");

  const visible = useMemo(() => {
    const sorted = [...stations];
    switch (sortKey) {
      case "signal":
        sorted.sort((a, b) => (b.signal_dbm ?? -Infinity) - (a.signal_dbm ?? -Infinity));
        break;
      case "hostname":
        sorted.sort((a, b) => (a.hostname ?? a.mac).localeCompare(b.hostname ?? b.mac));
        break;
      case "rate":
        sorted.sort((a, b) => (b.rx_rate ?? -1) - (a.rx_rate ?? -1));
        break;
      case "time":
        sorted.sort((a, b) => (b.connected_time ?? 0) - (a.connected_time ?? 0));
        break;
    }
    return sorted;
  }, [stations, sortKey]);

  if (stations.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No clients currently connected to a wireless network." />
      </div>
    );
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <span className="text-xs font-medium text-muted-foreground">Sort</span>
        {SORT_OPTIONS.map((option) => (
          <button
            key={option.value}
            type="button"
            onClick={() => setSortKey(option.value)}
            className={`rounded-md px-2.5 py-1 text-xs font-medium ${
              sortKey === option.value
                ? "bg-primary text-primary-foreground"
                : "border text-muted-foreground"
            }`}
          >
            {option.label}
          </button>
        ))}
      </div>

      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b bg-muted/40 text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">Hostname</th>
              <th className="px-3 py-2 font-medium">MAC</th>
              <th className="px-3 py-2 font-medium">IP</th>
              <th className="px-3 py-2 font-medium">Signal</th>
              <th className="px-3 py-2 font-medium">Noise</th>
              <th className="px-3 py-2 font-medium">RX Rate</th>
              <th className="px-3 py-2 font-medium">TX Rate</th>
              <th className="px-3 py-2 font-medium">Connected</th>
              <th className="px-3 py-2 font-medium">Interface</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((station) => (
              <tr key={station.mac} className="border-b last:border-0">
                <td className="px-3 py-2 font-medium">
                  {station.hostname ?? station.ssid ?? "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{station.mac}</td>
                <td className="px-3 py-2 font-mono text-xs">{station.ip ?? "—"}</td>
                <td className={`px-3 py-2 font-medium ${signalTone(station.signal_dbm)}`}>
                  {station.signal_dbm != null ? `${station.signal_dbm} dBm` : "—"}
                </td>
                <td className="px-3 py-2 text-muted-foreground">
                  {station.noise != null ? `${station.noise} dBm` : "—"}
                </td>
                <td className="px-3 py-2">
                  {station.rx_rate ? formatBitRate(station.rx_rate) : "—"}
                </td>
                <td className="px-3 py-2">
                  {station.tx_rate ? formatBitRate(station.tx_rate) : "—"}
                </td>
                <td className="px-3 py-2">
                  {station.connected_time != null
                    ? formatDuration(station.connected_time)
                    : "—"}
                </td>
                <td className="px-3 py-2 font-mono text-xs">{station.interface ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}