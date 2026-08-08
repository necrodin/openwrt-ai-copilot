"use client";

import { Activity, Boxes, CircleOff, Power } from "lucide-react";

import type { ServicesInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  services: ServicesInfo | null;
};

/**
 * Services overview: quick counts (total / running / enabled / stopped) and a
 * summary line describing how the live inventory was gathered.
 */
export function ServicesOverview({ services }: Props) {
  const total = services?.count ?? 0;
  const running = services?.running_count ?? 0;
  const enabled = services?.enabled_count ?? 0;
  const stopped = Math.max(0, total - running);

  const items = [
    {
      label: "Total services",
      value: String(total),
      icon: Boxes,
      sub: services ? `${services.services.length} init.d entries` : null,
    },
    {
      label: "Running",
      value: String(running),
      icon: Activity,
      sub: services ? "live processes right now" : null,
    },
    {
      label: "Enabled",
      value: String(enabled),
      icon: Power,
      sub: "start automatically at boot",
    },
    {
      label: "Stopped",
      value: String(stopped),
      icon: CircleOff,
      sub: "not currently running",
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
              {item.sub ? (
                <p className="text-xs text-muted-foreground">{item.sub}</p>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
      <div className="sm:col-span-2 xl:col-span-4">
        <StatusBadge
          tone={services ? (running === total ? "success" : "info") : "neutral"}
          label={
            services
              ? `${running} of ${total} services running · ${services.ubus ? "procd / ubus" : "init.d fallback"}`
              : "Service data loading…"
          }
        />
      </div>
    </div>
  );
}