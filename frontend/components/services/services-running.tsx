"use client";

import { ChevronRight } from "lucide-react";

import type { RouterService, ServicesInfo } from "@/lib/router-management";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/dashboard/widget";
import { formatDuration } from "@/lib/dashboard-utils";

type Props = {
  services: ServicesInfo | null;
  selectedName: string | null;
  onSelect: (name: string) => void;
};

/**
 * Running services: every service with a live process, its PID and uptime, and
 * a shortcut to open the full detail + action panel for that service.
 */
export function ServicesRunning({ services, selectedName, onSelect }: Props) {
  const running = (services?.services ?? []).filter((service) => service.running);

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold">Running services</h3>
            <p className="text-xs text-muted-foreground">
              {running.length} service{running.length === 1 ? "" : "s"} currently running
              {services ? ` of ${services.count} found` : ""}
            </p>
          </div>
        </div>

        {running.length === 0 ? (
          <EmptyState message="No service is currently running. Start one from the service actions panel." />
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Service</th>
                  <th className="px-3 py-2">PID</th>
                  <th className="px-3 py-2 text-right">Uptime</th>
                  <th className="px-3 py-2 text-right" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {running.map((service) => (
                  <ServiceRow
                    key={service.name}
                    service={service}
                    selected={service.name === selectedName}
                    onSelect={() => onSelect(service.name)}
                  />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function ServiceRow({
  service,
  selected,
  onSelect,
}: {
  service: RouterService;
  selected: boolean;
  onSelect: () => void;
}) {
  return (
    <tr
      className={`hover:bg-muted/40 ${selected ? "bg-muted/50" : ""}`}
      onClick={onSelect}
    >
      <td className="px-3 py-2">
        <div className="min-w-0 space-y-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <p className="font-mono text-xs font-medium">{service.name}</p>
            <StatusBadge label="Running" tone="success" />
          </div>
          <p className="max-w-md truncate text-xs text-muted-foreground">
            {service.description}
          </p>
        </div>
      </td>
      <td className="px-3 py-2 tabular-nums text-muted-foreground">
        {service.pid ?? "—"}
      </td>
      <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
        {service.uptime != null ? formatDuration(service.uptime) : "—"}
      </td>
      <td className="px-3 py-2 text-right">
        <Button variant="outline" size="sm" onClick={onSelect}>
          Manage
          <ChevronRight className="size-3" aria-hidden />
        </Button>
      </td>
    </tr>
  );
}