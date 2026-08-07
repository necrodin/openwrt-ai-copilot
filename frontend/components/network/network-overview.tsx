"use client";

import { Router } from "lucide-react";

import type { NetworkInterface, NetworkStatus } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { interfaceAddresses } from "@/lib/dashboard-utils";

type Props = {
  interfaces: NetworkInterface[];
  networkStatus: NetworkStatus | null;
  hostname: string;
};

function Stat({
  label,
  value,
  sub,
}: {
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="truncate text-lg font-semibold">{value || "—"}</p>
        {sub ? <p className="truncate text-xs text-muted-foreground">{sub}</p> : null}
      </CardContent>
    </Card>
  );
}

export function NetworkOverview({
  interfaces,
  networkStatus,
  hostname,
}: Props) {
  const wanIfaces = interfaces.filter((iface) => iface.name.startsWith("wan"));
  const lanIfaces = interfaces.filter(
    (iface) => iface.name.startsWith("lan") || iface.device?.startsWith("br-"),
  );
  const wanUp = wanIfaces.some((iface) => iface.up);
  const lanUp = lanIfaces.some((iface) => iface.up);
  const wanName =
    wanIfaces.find((iface) => iface.up)?.name ??
    wanIfaces.map((iface) => iface.name)[0];
  const lanName =
    lanIfaces.find((iface) => iface.up)?.name ??
    lanIfaces.map((iface) => iface.name)[0];
  const hasIpv4 = interfaces.some(
    (iface) => interfaceAddresses(iface, "ipv4").length > 0,
  );
  const hasIpv6 = interfaces.some(
    (iface) => interfaceAddresses(iface, "ipv6").length > 0,
  );
  const activeCount = interfaces.filter((iface) => iface.up).length;

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <div className="sm:col-span-2 xl:col-span-4">
        <div className="flex flex-wrap items-center gap-4 rounded-xl border p-4">
          <span className="flex size-11 shrink-0 items-center justify-center rounded-xl border bg-muted">
            <Router className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-base font-semibold">{hostname || "—"}</p>
            <p className="text-xs text-muted-foreground">
              Default gateway:{" "}
              <span className="font-mono font-medium text-foreground">
                {networkStatus?.gateway ?? "—"}
              </span>
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label="LAN" tone="neutral" />
            <StatusBadge
              label={wanUp ? "WAN up" : "WAN down"}
              tone={wanUp ? "success" : "danger"}
              dot
            />
          </div>
        </div>
      </div>

      <Stat label="WAN status" value={wanUp ? "Up" : "Down"} sub={wanName} />
      <Stat label="LAN status" value={lanUp ? "Up" : "Down"} sub={lanName} />
      <Stat
        label="Total interfaces"
        value={String(interfaces.length)}
        sub={`${activeCount} active`}
      />
      <Stat
        label="IPv4 connectivity"
        value={hasIpv4 ? "Available" : "Unavailable"}
        sub={hasIpv4 ? "Address assigned" : "No IPv4 address"}
      />
      <Stat
        label="IPv6 connectivity"
        value={hasIpv6 ? "Available" : "Unavailable"}
        sub={hasIpv6 ? "Address assigned" : "No IPv6 address"}
      />
    </div>
  );
}