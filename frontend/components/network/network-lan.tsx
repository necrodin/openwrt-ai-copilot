"use client";

import { Home } from "lucide-react";

import type { DhcpLease, NetworkInterface } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { ipv4PrefixToNetmask } from "@/lib/dashboard-utils";
import { Badge } from "@/components/ui/badge";

type Props = {
  lan: NetworkInterface | null;
  leases: DhcpLease[];
  dhcpEnabled: boolean;
};

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="truncate text-sm font-medium">{value || "—"}</span>
    </div>
  );
}

export function NetworkLan({ lan, leases, dhcpEnabled }: Props) {
  const ipv4 = lan
    ? lan.addresses.find((address) => address.family === "ipv4" && address.address)
    : null;
  const mask = lan?.addresses.some((a) => a.family === "ipv4")
    ? ipv4PrefixToNetmask(ipv4?.prefix ?? 0)
    : null;

  return (
    <Card>
      <CardContent className="space-y-1">
        <div className="mb-2 flex items-center justify-between">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <Home className="size-4 text-muted-foreground" aria-hidden />
            LAN
          </p>
          <StatusBadge
            label={lan?.up ? "Up" : "Down"}
            tone={lan?.up ? "success" : "danger"}
            dot
          />
        </div>
        <div className="space-y-1">
          <Row label="Interface" value={lan?.name ?? null} />
          <Row label="Address" value={ipv4?.address ?? null} />
          <Row label="Netmask" value={lan ? mask : null} />
          <Row label="DHCP" value={dhcpEnabled ? "Enabled" : "Disabled"} />
          <Row label="Connected clients" value={String(leases.length)} />
        </div>
        {lan && lan.bridge_members.length > 0 ? (
          <div className="pt-2">
            <p className="mb-1.5 text-xs uppercase tracking-wide text-muted-foreground">
              Bridge members
            </p>
            <div className="flex flex-wrap gap-1.5">
              {lan.bridge_members.map((member) => (
                <Badge key={member} variant="secondary">
                  {member}
                </Badge>
              ))}
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}