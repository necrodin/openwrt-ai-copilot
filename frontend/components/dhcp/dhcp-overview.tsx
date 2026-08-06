"use client";

import { Globe, Network, Server, Timer } from "lucide-react";

import type { DhcpInfo } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  dhcp: DhcpInfo;
};

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="truncate text-sm font-medium">{value || "—"}</span>
    </div>
  );
}

export function DhcpOverview({ dhcp }: Props) {
  const pool = dhcp.pools[0];
  const range = pool?.start
    ? pool.range_end
      ? `${pool.start} – ${pool.range_end}`
      : pool.start
    : null;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardContent className="space-y-1">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Server className="size-4 text-muted-foreground" aria-hidden />
            DNSMASQ
          </p>
          <div className="space-y-1">
            <Row label="Enabled" value={dhcp.enabled ? "Yes" : "No"} />
            <Row label="Interface" value={pool?.interface ?? null} />
            <Row label="Lease Time" value={pool?.leasetime ?? null} />
            <Row label="DHCP Range" value={range ?? null} />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-1">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Network className="size-4 text-muted-foreground" aria-hidden />
            NETWORK
          </p>
          <div className="space-y-1">
            <Row label="Gateway" value={dhcp.gateway ?? null} />
            <Row label="DNS" value={dhcp.dns.join(", ") || null} />
            <Row label="Domain" value={dhcp.domain ?? null} />
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-4 rounded-xl border p-4 lg:col-span-2">
        <div className="flex items-center gap-2 text-sm">
          <Globe className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">Server</span>
        </div>
        <StatusBadge
          label={dhcp.enabled ? "Running" : "Stopped"}
          tone={dhcp.enabled ? "success" : "danger"}
          dot
        />
        <StatusBadge
          label={`${dhcp.pools.length} pool${dhcp.pools.length === 1 ? "" : "s"}`}
          tone="neutral"
          dot={false}
        />
        <StatusBadge
          label={`${dhcp.static_leases.length} static lease${dhcp.static_leases.length === 1 ? "" : "s"}`}
          tone="neutral"
          dot={false}
        />
        {dhcp.leases.length > 0 ? (
          <div className="flex items-center gap-2 text-sm">
            <Timer className="size-4 text-muted-foreground" aria-hidden />
            <span className="text-muted-foreground">Active</span>
            <span className="font-medium">{dhcp.leases.length} leases</span>
          </div>
        ) : null}
      </div>
    </div>
  );
}