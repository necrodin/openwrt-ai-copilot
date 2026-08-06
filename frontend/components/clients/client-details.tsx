import { MonitorSmartphone } from "lucide-react";

import { InfoItem } from "@/components/router/info-item";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import type { NetworkClient } from "@/lib/clients";
import { formatBytes, formatClock } from "@/lib/dashboard-utils";

type Props = {
  client: NetworkClient;
};

const SOURCE_LABELS: Record<string, string> = {
  dhcp: "DHCP",
  arp: "ARP",
  wifi: "WiFi",
  neighbor: "IPv6",
};

function formatLease(expires: string | null): string {
  if (expires === null) {
    return "—";
  }
  const epochSeconds = Number(expires);
  if (Number.isFinite(epochSeconds)) {
    const date = new Date(epochSeconds * 1000);
    if (!Number.isNaN(date.getTime())) {
      return formatClock(date.toISOString());
    }
  }
  return expires;
}

export function ClientDetails({ client }: Props) {
  const label =
    client.hostname ??
    client.mac ??
    client.ipv4 ??
    client.ipv6 ??
    "Unknown device";

  return (
    <Card className="gap-4">
      <CardHeader className="px-4 pb-0">
        <CardTitle className="flex items-center gap-2 text-sm">
          <span className="flex size-8 shrink-0 items-center justify-center rounded-lg border bg-muted">
            <MonitorSmartphone className="size-4 text-muted-foreground" aria-hidden />
          </span>
          <span className="truncate">{label}</span>
        </CardTitle>
        <div className="flex flex-wrap items-center gap-1.5 pt-1">
          <StatusBadge
            label={client.online ? "Online" : "Offline"}
            tone={client.online ? "success" : "danger"}
          />
          <StatusBadge
            label={
              client.medium === "unknown"
                ? "Unknown"
                : client.medium === "wired"
                  ? "Wired"
                  : "Wireless"
            }
            tone={client.medium === "wireless" ? "info" : "neutral"}
          />
          {client.sources.map((source) => (
            <Badge key={source} variant="outline">
              {SOURCE_LABELS[source] ?? source}
            </Badge>
          ))}
        </div>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-4 px-4 sm:grid-cols-2">
        <InfoItem label="Hostname" value={client.hostname ?? "—"} />
        <InfoItem label="IP" value={client.ipv4 ?? "—"} mono />
        <InfoItem label="IPv6" value={client.ipv6 ?? "—"} mono />
        <InfoItem label="MAC" value={client.mac ?? "—"} mono />
        <InfoItem label="Vendor" value={client.vendor ?? "—"} />
        <InfoItem label="Interface" value={client.interface ?? "—"} mono />
        <InfoItem label="SSID" value={client.ssid ?? "—"} />
        <InfoItem label="Signal" value={client.signal_dbm !== null ? `${client.signal_dbm} dBm` : "—"} mono />
        <InfoItem label="RX" value={client.rx_bytes !== null ? formatBytes(client.rx_bytes) : "—"} mono />
        <InfoItem label="TX" value={client.tx_bytes !== null ? formatBytes(client.tx_bytes) : "—"} mono />
        <InfoItem
          label="Connected"
          value={
            client.connected_minutes !== null
              ? `${client.connected_minutes} min`
              : "—"
          }
          mono
        />
        <InfoItem
          label="Lease"
          value={
            client.lease_active === null
              ? "—"
              : `${client.lease_active ? "Active" : "Expired"} · ${formatLease(client.lease_expires)}`
          }
          mono
        />
        <InfoItem label="Last seen" value={client.last_seen ? formatClock(client.last_seen) : "—"} mono />
        <InfoItem label="Status" value={client.arp_state ?? "—"} mono />
      </CardContent>
    </Card>
  );
}
