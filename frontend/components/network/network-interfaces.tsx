"use client";

import { useState } from "react";

import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import type {
  FirewallZone,
  NetworkInterface,
  RouteEntry,
} from "@/lib/dashboard";
import {
  formatBytes,
  interfaceAddresses,
} from "@/lib/dashboard-utils";

type Props = {
  interfaces: NetworkInterface[];
  zones: FirewallZone[];
  routing: RouteEntry[];
  dns: string[];
  busy?: boolean;
  onEnable: (section: string) => void;
  onDisable: (section: string) => void;
  onRestart: (section: string) => void;
};

type Pending =
  | { kind: "enable"; section: string; name: string }
  | { kind: "disable"; section: string; name: string }
  | { kind: "restart"; section: string; name: string }
  | null;

export function NetworkInterfaces({
  interfaces,
  zones,
  routing,
  dns,
  busy = false,
  onEnable,
  onDisable,
  onRestart,
}: Props) {
  const [pending, setPending] = useState<Pending>(null);

  const zoneFor = (name: string): string | null => {
    const match = zones.find(
      (zone) =>
        zone.network.includes(name) || zone.name === name,
    );
    return match?.name ?? null;
  };

  const metricFor = (iface: NetworkInterface): number | null => {
    const route = routing.find((r) => r.interface === iface.name);
    return route?.metric ?? null;
  };

  const run = (action: Pending) => {
    if (!action) {
      return;
    }
    setPending(null);
    if (action.kind === "enable") {
      onEnable(action.section);
    } else if (action.kind === "disable") {
      onDisable(action.section);
    } else if (action.kind === "restart") {
      onRestart(action.section);
    }
  };

  if (interfaces.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No network interfaces discovered." />
      </div>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b text-left text-xs text-muted-foreground">
              <th className="px-3 py-2.5 font-medium">Interface</th>
              <th className="px-3 py-2.5 font-medium">Protocol</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Device</th>
              <th className="hidden px-3 py-2.5 font-medium lg:table-cell">Zone</th>
              <th className="px-3 py-2.5 font-medium">Status</th>
              <th className="hidden px-3 py-2.5 font-medium xl:table-cell">IPv4</th>
              <th className="hidden px-3 py-2.5 font-medium xl:table-cell">IPv6</th>
              <th className="hidden px-3 py-2.5 font-medium md:table-cell">Gateway</th>
              <th className="hidden px-3 py-2.5 font-medium lg:table-cell">DNS</th>
              <th className="hidden px-3 py-2.5 font-medium lg:table-cell">RX / TX</th>
              <th className="hidden px-3 py-2.5 font-medium sm:table-cell">MTU</th>
              <th className="hidden px-3 py-2.5 font-medium sm:table-cell">Metric</th>
              <th className="px-3 py-2.5 font-medium">Actions</th>
            </tr>
          </thead>
          <tbody>
            {interfaces.map((iface) => {
              const ipv4 = interfaceAddresses(iface, "ipv4");
              const ipv6 = interfaceAddresses(iface, "ipv6");
              const metric = metricFor(iface);
              const zone = zoneFor(iface.name);
              return (
                <tr
                  key={iface.name}
                  className="border-b last:border-b-0 hover:bg-accent/40"
                >
                  <td className="px-3 py-2 font-medium">{iface.name}</td>
                  <td className="px-3 py-2 text-xs">{iface.proto ?? "—"}</td>
                  <td className="hidden px-3 py-2 font-mono text-xs md:table-cell">
                    {iface.device ?? "—"}
                  </td>
                  <td className="hidden px-3 py-2 lg:table-cell">{zone ?? "—"}</td>
                  <td className="px-3 py-2">
                    <StatusBadge
                      label={iface.up ? "Up" : "Down"}
                      tone={iface.up ? "success" : "danger"}
                      dot
                    />
                  </td>
                  <td className="hidden px-3 py-2 font-mono text-xs xl:table-cell">
                    {ipv4.join(", ") || "—"}
                  </td>
                  <td className="hidden px-3 py-2 font-mono text-xs xl:table-cell">
                    {ipv6.join(", ") || "—"}
                  </td>
                  <td className="hidden px-3 py-2 font-mono text-xs md:table-cell">
                    {iface.gateway ?? "—"}
                  </td>
                  <td className="hidden max-w-32 truncate px-3 py-2 font-mono text-xs lg:table-cell">
                    {iface.name.startsWith("wan") ? dns.join(", ") || "—" : "—"}
                  </td>
                  <td className="hidden whitespace-nowrap px-3 py-2 tabular-nums lg:table-cell">
                    {iface.rx_bytes !== null || iface.tx_bytes !== null
                      ? `↓ ${formatBytes(iface.rx_bytes)} ↑ ${formatBytes(iface.tx_bytes)}`
                      : "—"}
                  </td>
                  <td className="hidden px-3 py-2 tabular-nums sm:table-cell">
                    {iface.mtu ?? "—"}
                  </td>
                  <td className="hidden px-3 py-2 tabular-nums sm:table-cell">
                    {metric ?? "—"}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2">
                    <div className="flex items-center gap-1">
                      {iface.up ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busy}
                          onClick={() =>
                            setPending({ kind: "disable", section: iface.name, name: iface.name })
                          }
                        >
                          Disable
                        </Button>
                      ) : (
                        <Button
                          size="sm"
                          disabled={busy}
                          onClick={() =>
                            setPending({ kind: "enable", section: iface.name, name: iface.name })
                          }
                        >
                          Enable
                        </Button>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          setPending({ kind: "restart", section: iface.name, name: iface.name })
                        }
                      >
                        Restart
                      </Button>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <ConfirmDialog
        open={pending?.kind === "enable"}
        title={`Enable ${pending?.name}?`}
        description={`The ${pending?.name} interface will be brought up and the network configuration reloaded.`}
        confirmLabel="Enable"
        tone="default"
        busy={busy}
        onConfirm={() => run(pending)}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending?.kind === "disable"}
        title={`Disable ${pending?.name}?`}
        description={`The ${pending?.name} interface will be taken down. Clients on this network will lose connectivity until it is re-enabled.`}
        confirmLabel="Disable"
        busy={busy}
        onConfirm={() => run(pending)}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending?.kind === "restart"}
        title={`Restart ${pending?.name}?`}
        description={`The ${pending?.name} interface will be restarted (brought down and up again).`}
        confirmLabel="Restart"
        busy={busy}
        onConfirm={() => run(pending)}
        onCancel={() => setPending(null)}
      />
    </>
  );
}