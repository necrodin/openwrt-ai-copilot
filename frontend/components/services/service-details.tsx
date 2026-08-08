"use client";

import { ServerCog } from "lucide-react";
import type { ReactNode } from "react";

import type { RouterService } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/dashboard/widget";
import { formatDuration } from "@/lib/dashboard-utils";

type Props = {
  service: RouterService | null;
  ubus: boolean;
};

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-4 py-1.5">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="text-sm tabular-nums">{value}</span>
    </div>
  );
}

/**
 * Service details: full read-only breakdown for a selected service — its state
 * badges, PID, uptime, restart count and instance count.
 */
export function ServiceDetails({ service, ubus }: Props) {
  if (service === null) {
    return (
      <Card>
        <CardContent>
          <EmptyState message="Select a service from the lists above to see its details and controls." />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <ServerCog className="size-4 text-muted-foreground" aria-hidden />
            {service.name}
          </h3>
          <p className="text-sm text-muted-foreground">{service.description}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {service.running ? (
            <StatusBadge label="Running" tone="success" />
          ) : (
            <StatusBadge label="Stopped" tone="neutral" />
          )}
          {service.enabled === null ? (
            <StatusBadge label="Boot state unknown" tone="warning" />
          ) : service.enabled ? (
            <StatusBadge label="Enabled at boot" tone="success" />
          ) : (
            <StatusBadge label="Disabled at boot" tone="neutral" />
          )}
          <StatusBadge
            label={ubus ? "procd / ubus" : "init.d fallback"}
            tone="info"
          />
        </div>

        <div className="divide-y rounded-md border px-3 py-1">
          <Row label="PID" value={service.pid != null ? String(service.pid) : "—"} />
          <Row
            label="Uptime"
            value={service.uptime != null ? formatDuration(service.uptime) : "—"}
          />
          <Row
            label="Restart count"
            value={service.restart_count != null ? String(service.restart_count) : "—"}
          />
          <Row label="Instances" value={String(service.instances)} />
        </div>
      </CardContent>
    </Card>
  );
}