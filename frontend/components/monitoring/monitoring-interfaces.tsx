"use client";

import type { NetworkInterface } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatBytes } from "@/lib/dashboard-utils";

type Props = {
  interfaces: NetworkInterface[];
};

function Stat({ label, value, danger }: { label: string; value: string | number | null; danger?: boolean }) {
  return (
    <div className="px-3 py-2 text-right">
      <p className="text-[0.65rem] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </p>
      <p className={`tabular-nums ${danger ? "text-red-600 dark:text-red-400" : ""}`}>
        {value ?? "—"}
      </p>
    </div>
  );
}

export function MonitoringInterfaces({ interfaces }: Props) {
  const upCount = interfaces.filter((iface) => iface.up).length;

  return (
    <Card>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Network interfaces</h3>
          <p className="text-xs text-muted-foreground">
            {interfaces.length} interface{interfaces.length === 1 ? "" : "s"} · {upCount} up
          </p>
        </div>

        {interfaces.length === 0 ? (
          <p className="rounded-md border border-dashed px-3 py-8 text-center text-sm text-muted-foreground">
            No interface data available.
          </p>
        ) : (
          <div className="space-y-3">
            {interfaces.map((iface) => (
              <Card key={iface.name} className="bg-muted/30">
                <CardContent className="space-y-3 p-4">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-sm font-medium">{iface.name}</span>
                      {iface.is_bridge ? (
                        <span className="rounded bg-muted px-1.5 py-0.5 text-[0.65rem] uppercase tracking-wide text-muted-foreground">
                          bridge
                        </span>
                      ) : null}
                      <span className="text-xs text-muted-foreground">{iface.proto ?? "—"}</span>
                    </div>
                    <div className="flex items-center gap-2">
                      <StatusBadge
                        tone={iface.up ? "success" : "danger"}
                        label={iface.up ? "Up" : "Down"}
                      />
                      {iface.link !== null ? (
                        <StatusBadge
                          tone={iface.link ? "success" : "warning"}
                          label={iface.link ? "Linked" : "No link"}
                        />
                      ) : null}
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                    {iface.speed_mbps != null ? (
                      <span>Link {iface.speed_mbps} Mbps</span>
                    ) : null}
                    {iface.mtu != null ? <span>MTU {iface.mtu}</span> : null}
                    {iface.mac ? (
                      <span className="font-mono">MAC {iface.mac}</span>
                    ) : null}
                    {iface.gateway ? <span>GW {iface.gateway}</span> : null}
                    {iface.addresses.length > 0 ? (
                      <span className="font-mono">
                        {iface.addresses.map((address) => address.address ?? "").join(" · ")}
                      </span>
                    ) : null}
                  </div>

                  <div className="grid grid-cols-2 gap-x-2 rounded-md border bg-background sm:grid-cols-6">
                    <Stat label="RX" value={formatBytes(iface.rx_bytes)} />
                    <Stat label="TX" value={formatBytes(iface.tx_bytes)} />
                    <Stat
                      label="RX err"
                      value={iface.rx_errors ?? null}
                      danger={(iface.rx_errors ?? 0) > 0}
                    />
                    <Stat
                      label="RX drop"
                      value={iface.rx_dropped ?? null}
                      danger={(iface.rx_dropped ?? 0) > 0}
                    />
                    <Stat
                      label="TX err"
                      value={iface.tx_errors ?? null}
                      danger={(iface.tx_errors ?? 0) > 0}
                    />
                    <Stat
                      label="TX drop"
                      value={iface.tx_dropped ?? null}
                      danger={(iface.tx_dropped ?? 0) > 0}
                    />
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}