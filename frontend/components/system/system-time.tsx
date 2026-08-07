"use client";

import { Clock, RadioTower } from "lucide-react";

import type { SystemInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  system: SystemInfo;
  busy?: boolean;
  onSyncTime: () => void;
  onRestartNtp: () => void;
};

function formatEpoch(epoch: number | null): string {
  if (epoch === null || Number.isNaN(epoch)) {
    return "—";
  }
  return new Date(epoch * 1000).toLocaleString([], {
    dateStyle: "medium",
    timeStyle: "medium",
  });
}

export function SystemTime({ system, busy = false, onSyncTime, onRestartNtp }: Props) {
  const offset = system.ntp.offset;

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Time</h3>
            <p className="text-xs text-muted-foreground">Router clock, NTP and sync.</p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" onClick={onRestartNtp} disabled={busy}>
              <RadioTower className="size-4" aria-hidden />
              Restart NTP
            </Button>
            <Button variant="outline" size="sm" onClick={onSyncTime} disabled={busy}>
              <Clock className="size-4" aria-hidden />
              Sync time
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Router time
            </p>
            <p className="text-sm font-semibold" title={system.local_time}>
              {system.local_time || "—"}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              Boot time
            </p>
            <p className="text-sm font-semibold">{formatEpoch(system.boot_time)}</p>
          </div>
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
              NTP sync
            </p>
            <div className="flex items-center gap-2">
              <StatusBadge
                tone={system.ntp.enabled ? "success" : "warning"}
                label={system.ntp.enabled ? "Enabled" : "Disabled"}
              />
              {offset !== null ? (
                <span className="text-xs tabular-nums text-muted-foreground">
                  offset {offset > 0 ? "+" : ""}
                  {offset.toFixed(3)}s
                </span>
              ) : null}
            </div>
          </div>
        </div>

        <div className="space-y-2">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Active NTP servers
          </p>
          {system.ntp.servers.length === 0 ? (
            <p className="rounded-md border border-dashed px-3 py-4 text-center text-sm text-muted-foreground">
              No NTP servers configured on the router.
            </p>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {system.ntp.servers.map((server) => (
                <li
                  key={server}
                  className="rounded-md border bg-muted/40 px-2.5 py-1 font-mono text-xs"
                >
                  {server}
                </li>
              ))}
            </ul>
          )}
        </div>
      </CardContent>
    </Card>
  );
}