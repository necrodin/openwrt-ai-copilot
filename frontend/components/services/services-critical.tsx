"use client";

import { ShieldCheck } from "lucide-react";

import type { ServiceInfo } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/dashboard/widget";

type Props = {
  services: ServiceInfo[];
  loading?: boolean;
};

function toneFor(configured: boolean, running: boolean, enabled: boolean) {
  if (!configured) return "neutral";
  if (running && enabled) return "success";
  if (running) return "info";
  if (enabled) return "warning";
  return "danger";
}

function labelFor(configured: boolean, running: boolean, enabled: boolean) {
  if (!configured) return "Not configured";
  if (running && enabled) return "Running";
  if (running) return "Running (not enabled)";
  if (enabled) return "Enabled (stopped)";
  return "Stopped";
}

/**
 * Critical services: the curated set probed by the snapshot collector
 * (firewall, dnsmasq, hostapd, dropbear, VPN, QoS, …) with their configured,
 * enabled and running signals.
 */
export function ServicesCritical({ services, loading = false }: Props) {
  if (loading && services.length === 0) {
    return (
      <Card>
        <CardContent>
          <EmptyState message="Loading critical services…" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h3 className="flex items-center gap-2 text-sm font-semibold">
              <ShieldCheck className="size-4 text-muted-foreground" aria-hidden />
              Critical services
            </h3>
            <p className="text-xs text-muted-foreground">
              Health of the services that keep the router secure and reachable.
            </p>
          </div>
        </div>

        {services.length === 0 ? (
          <EmptyState message="No critical service data has been collected yet." />
        ) : (
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {services.map((service) => {
              const tone = toneFor(service.configured, service.running, service.enabled);
              return (
                <div
                  key={service.name}
                  className="flex items-start justify-between gap-3 rounded-md border px-3 py-3"
                >
                  <div className="min-w-0 space-y-0.5">
                    <p className="font-mono text-xs font-medium">{service.name}</p>
                    {service.detail ? (
                      <p className="truncate text-xs text-muted-foreground">
                        {service.detail}
                      </p>
                    ) : null}
                  </div>
                  <StatusBadge
                    tone={tone}
                    label={labelFor(service.configured, service.running, service.enabled)}
                  />
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}