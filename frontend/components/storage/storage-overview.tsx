"use client";

import { Database, HardDrive, Layers, Usb } from "lucide-react";

import type { StorageInfo } from "@/lib/router-management";
import { formatBytes } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { Gauge } from "@/components/dashboard/gauge";

type Props = {
  storage: StorageInfo | null;
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

export function StorageOverview({ storage }: Props) {
  const root = storage?.rootfs ?? null;
  const overlay = storage?.overlayfs ?? null;
  const percent = storage?.use_percent ?? root?.use_percent ?? null;

  const items = [
    {
      label: "Root filesystem",
      value: percent !== null ? `${percent}% used` : "—",
      icon: Database,
      sub: root
        ? `${formatBytes(root.used_bytes)} of ${formatBytes(root.total_bytes)} · ${root.filesystem || "rootfs"}`
        : storage
          ? "waiting for rootfs data"
          : null,
      gauge: percent,
    },
    {
      label: "Overlay",
      value: overlay ? overlay.use_percent !== null ? `${overlay.use_percent}%` : "—" : "None",
      icon: Layers,
      sub: overlay
        ? `${formatBytes(overlay.used_bytes)} of ${formatBytes(overlay.total_bytes)} · ${overlay.mountpoint}`
        : "using persistent overlay",
      gauge: overlay?.use_percent ?? null,
    },
    {
      label: "Block devices",
      value: String(storage?.devices.length ?? 0),
      icon: HardDrive,
      sub: storage
        ? `${formatBytes(storage.devices.reduce((sum, device) => sum + device.size, 0))} total`
        : "waiting for device data",
    },
    {
      label: "USB storage",
      value: String(storage?.usb.length ?? 0),
      icon: Usb,
      sub: storage
        ? `${storage.usb.filter((device) => device.mounted).length} mounted`
        : "waiting for USB data",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Card key={item.label}>
            <CardContent className="space-y-2">
              <div className="flex items-center gap-2">
                <Icon className="size-4 text-muted-foreground" aria-hidden />
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {item.label}
                </p>
              </div>
              <p className="text-2xl font-semibold tabular-nums">{item.value}</p>
              {item.sub ? <p className="text-xs text-muted-foreground">{item.sub}</p> : null}
              {"gauge" in item && item.gauge !== undefined ? (
                <Gauge value={item.gauge ?? 0} tone={tone(item.gauge ?? null)} />
              ) : null}
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}