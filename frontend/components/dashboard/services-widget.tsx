import { ServerCog } from "lucide-react";

import type { ServiceInfo } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  services: ServiceInfo[];
  loading?: boolean;
  error?: string | null;
};

function stateBadge(service: ServiceInfo): {
  label: string;
  tone: "default" | "secondary" | "destructive" | "outline";
} {
  if (!service.configured) {
    return { label: "Not configured", tone: "secondary" };
  }
  if (service.running) {
    return { label: "Running", tone: "default" };
  }
  return { label: "Stopped", tone: "destructive" };
}

export function ServicesWidget({ services, loading = false, error = null }: Props) {
  const configured = services.filter((service) => service.configured);

  if (services.length === 0) {
    return (
      <Widget title="Services" icon={ServerCog} loading={loading} error={error}>
        <EmptyState message="No service telemetry available." />
      </Widget>
    );
  }

  return (
    <Widget
      title="Services"
      icon={ServerCog}
      subtitle={`${configured.length} of ${services.length} configured`}
      className="lg:col-span-3"
      loading={loading}
      error={error}
    >
      <div className="flex flex-wrap gap-2">
        {services.map((service) => {
          const badge = stateBadge(service);
          return (
            <div
              key={service.name}
              className={cn(
                "flex items-center gap-3 rounded-md border px-3 py-2",
                service.running ? "border-emerald-500/30 bg-emerald-500/5" : "border-border",
              )}
            >
              <div className="min-w-0">
                <p className="flex items-center gap-2 text-sm font-medium">
                  <span className="capitalize">{service.name}</span>
                  {service.version ? (
                    <span className="text-xs text-muted-foreground">{service.version}</span>
                  ) : null}
                </p>
                <p className="text-[11px] text-muted-foreground">
                  {service.enabled ? "enabled on boot" : "not enabled on boot"}
                </p>
              </div>
              <Badge variant={badge.tone}>{badge.label}</Badge>
            </div>
          );
        })}
      </div>
    </Widget>
  );
}