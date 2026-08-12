"use client";

import { Globe } from "lucide-react";

import type { NetworkInterface } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { formatBytes, formatDuration, wanAddressLabel } from "@/lib/dashboard-utils";

type Props = {
  wan: NetworkInterface | null;
  dns: string[];
};

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="truncate text-sm font-medium">{value || "—"}</span>
    </div>
  );
}

export function NetworkWan({ wan, dns }: Props) {
  const wanIpv4 = wan
    ? wan.addresses.find((address) => address.family === "ipv4" && address.address) ?? null
    : null;

  return (
    <Card>
      <CardContent className="space-y-1">
        <div className="mb-2 flex items-center justify-between">
          <p className="flex items-center gap-2 text-sm font-semibold">
            <Globe className="size-4 text-muted-foreground" aria-hidden />
            WAN
          </p>
          <StatusBadge
            label={wan?.up ? "Up" : "Down"}
            tone={wan?.up ? "success" : "danger"}
            dot
          />
        </div>
        <div className="space-y-1">
          <Row label="Interface" value={wan?.name ?? null} />
          <Row label="Protocol" value={wan?.proto ?? null} />
          <Row label={wanAddressLabel(wanIpv4?.is_public ?? null)} value={wanIpv4?.address ?? null} />
          <Row label="Gateway" value={wan?.gateway ?? null} />
          <Row label="DNS" value={dns.join(", ") || null} />
          <Row
            label="Uptime"
            value={
              wan?.uptime_seconds != null
                ? formatDuration(wan.uptime_seconds)
                : null
            }
          />
          <Row
            label="Traffic"
            value={
              wan && wan.rx_bytes != null && wan.tx_bytes != null
                ? `↓ ${formatBytes(wan.rx_bytes)} ↑ ${formatBytes(wan.tx_bytes)}`
                : null
            }
          />
          <Row label="MTU" value={wan && wan.mtu != null ? String(wan.mtu) : null} />
        </div>
      </CardContent>
    </Card>
  );
}