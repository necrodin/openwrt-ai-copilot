"use client";

import { HardDrive } from "lucide-react";

import type { StorageInfo } from "@/lib/router-management";
import { formatBytes } from "@/lib/format";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";
import { cn } from "@/lib/utils";

type Props = {
  storage: StorageInfo | null;
};

function statusTone(status: string): "success" | "warning" | "neutral" {
  if (status === "mounted") {
    return "success";
  }
  if (status === "online") {
    return "warning";
  }
  return "neutral";
}

/**
 * Physical block devices reported by the router (eMMC / SD, USB storage,
 * generic disks). Read-only inventory with capacity and mount state.
 */
export function StorageDevices({ storage }: Props) {
  const devices = storage?.devices ?? [];

  return (
    <Widget
      title="Block devices"
      icon={HardDrive}
      subtitle={
        storage
          ? `${devices.length} device${devices.length === 1 ? "" : "s"} detected`
          : "Storage inventory loading…"
      }
    >
      {devices.length === 0 ? (
        <EmptyState message="No block devices were reported by the router." />
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">Device</th>
                <th className="px-3 py-2 font-medium">Type</th>
                <th className="px-3 py-2 font-medium">Model</th>
                <th className="px-3 py-2 font-medium">Capacity</th>
                <th className="px-3 py-2 font-medium">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {devices.map((device) => {
                const model = [device.vendor, device.model].filter(Boolean).join(" ") || "—";
                return (
                  <tr key={device.name}>
                    <td className="px-3 py-2 font-mono text-xs font-medium">{device.name}</td>
                    <td className="px-3 py-2">{device.type}</td>
                    <td className="px-3 py-2">{model}</td>
                    <td className="px-3 py-2 tabular-nums">{formatBytes(device.size)}</td>
                    <td className="px-3 py-2">
                      <Badge
                        variant="outline"
                        className={cn(
                          device.status === "mounted"
                            ? "border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
                            : device.status === "online"
                              ? "border-amber-500/40 text-amber-700 dark:text-amber-400"
                              : "",
                        )}
                      >
                        <span
                          className={cn(
                            "mr-1.5 inline-block size-1.5 rounded-full",
                            statusTone(device.status) === "success"
                              ? "bg-emerald-500"
                              : statusTone(device.status) === "warning"
                                ? "bg-amber-500"
                                : "bg-muted-foreground",
                          )}
                          aria-hidden
                        />
                        {device.status}
                      </Badge>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Widget>
  );
}