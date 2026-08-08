"use client";

import { ChevronRight } from "lucide-react";

import type { RouterService, ServicesInfo } from "@/lib/router-management";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/dashboard/widget";

type Props = {
  services: ServicesInfo | null;
  selectedName: string | null;
  onSelect: (name: string) => void;
};

/**
 * Enabled services: those marked to start at boot, with their current running
 * state and a shortcut to manage each one.
 */
export function ServicesEnabled({ services, selectedName, onSelect }: Props) {
  const enabled = (services?.services ?? []).filter((service) => service.enabled === true);

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="text-sm font-semibold">Enabled services</h3>
            <p className="text-xs text-muted-foreground">
              {enabled.length} service{enabled.length === 1 ? "" : "s"} start automatically at boot
            </p>
          </div>
        </div>

        {enabled.length === 0 ? (
          <EmptyState message="No service is enabled to start at boot yet." />
        ) : (
          <div className="overflow-x-auto rounded-md border">
            <table className="w-full min-w-[38rem] text-left text-sm">
              <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Service</th>
                  <th className="px-3 py-2">State</th>
                  <th className="px-3 py-2 text-right" />
                </tr>
              </thead>
              <tbody className="divide-y">
                {enabled.map((service) => (
                  <EnabledRow
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

function EnabledRow({
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
          <p className="font-mono text-xs font-medium">{service.name}</p>
          <p className="max-w-md truncate text-xs text-muted-foreground">
            {service.description}
          </p>
        </div>
      </td>
      <td className="px-3 py-2">
        {service.running ? (
          <StatusBadge label="Running" tone="success" />
        ) : (
          <StatusBadge label="Stopped" tone="neutral" />
        )}
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