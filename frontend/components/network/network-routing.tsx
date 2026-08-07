"use client";

import type { RouteEntry } from "@/lib/dashboard";
import { EmptyState } from "@/components/dashboard/widget";
import { Badge } from "@/components/ui/badge";

type Props = {
  routes: RouteEntry[];
};

const DEFAULT_TARGETS = new Set(["0.0.0.0", "0.0.0.0/0", "default", "::", "::/0"]);

export function NetworkRouting({ routes }: Props) {
  const defaults = routes.filter((route) => DEFAULT_TARGETS.has(route.destination));
  const statics = routes.filter((route) => !DEFAULT_TARGETS.has(route.destination));

  const renderTable = (rows: RouteEntry[], empty: string) =>
    rows.length === 0 ? (
      <p className="py-8 text-center text-sm text-muted-foreground">{empty}</p>
    ) : (
      <div className="overflow-x-auto rounded-lg border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="px-3 py-2 font-medium">Destination</th>
              <th className="px-3 py-2 font-medium">Gateway</th>
              <th className="px-3 py-2 font-medium">Metric</th>
              <th className="px-3 py-2 font-medium">Interface</th>
              <th className="px-3 py-2 font-medium">Family</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((route, index) => (
              <tr key={index} className="border-b last:border-b-0 hover:bg-accent/40">
                <td className="px-3 py-2 font-mono text-xs">{route.destination}</td>
                <td className="px-3 py-2 font-mono text-xs">{route.gateway ?? "—"}</td>
                <td className="px-3 py-2 tabular-nums">{route.metric ?? "—"}</td>
                <td className="px-3 py-2 font-mono text-xs">{route.interface ?? "—"}</td>
                <td className="px-3 py-2">
                  <Badge variant={route.family === "ipv4" ? "secondary" : "outline"}>
                    {route.family}
                  </Badge>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );

  if (routes.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No routes discovered." />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-6">
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Default routes</h3>
        {renderTable(defaults, "No default route configured.")}
      </div>
      <div className="space-y-2">
        <h3 className="text-sm font-semibold">Static routes</h3>
        {renderTable(statics, "No static routes configured.")}
      </div>
    </div>
  );
}