"use client";

import { Radio, Satellite, Users, Wifi } from "lucide-react";

import type { WifiInfo } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  wifi: WifiInfo;
};

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <Card>
      <CardContent className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
          {icon}
        </span>
        <div className="min-w-0">
          <p className="text-2xl font-bold leading-none">{value}</p>
          <p className="mt-1 truncate text-xs text-muted-foreground">{label}</p>
        </div>
      </CardContent>
    </Card>
  );
}

export function WirelessOverview({ wifi }: Props) {
  const ssidCount = wifi.networks.length;
  const enabledSsidCount = wifi.networks.filter((network) => network.enabled).length;
  const connected = wifi.radios.reduce((sum, radio) => sum + radio.station_count, 0);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        icon={<Radio className="size-5 text-muted-foreground" aria-hidden />}
        label="Radios"
        value={String(wifi.radios.length)}
      />
      <StatCard
        icon={<Wifi className="size-5 text-muted-foreground" aria-hidden />}
        label={`SSIDs (${enabledSsidCount} enabled)`}
        value={String(ssidCount)}
      />
      <StatCard
        icon={<Users className="size-5 text-muted-foreground" aria-hidden />}
        label="Connected clients"
        value={String(connected)}
      />
      <Card>
        <CardContent className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <Satellite className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0 space-y-1.5">
            {wifi.radios.map((radio) => (
              <div key={radio.name} className="flex flex-wrap items-center gap-1.5 text-xs">
                <StatusBadge
                  label={radio.up ? "up" : "down"}
                  tone={radio.up ? "success" : "neutral"}
                  dot
                />
                <span className="font-medium">{radio.name}</span>
                {radio.band ? <Badge variant="outline">{radio.band}</Badge> : null}
                {radio.channel ? <span>ch {radio.channel}</span> : null}
                {radio.width_mhz ? <span>· {radio.width_mhz} MHz</span> : null}
                {radio.country ? <span>· {radio.country}</span> : null}
                {radio.tx_power != null ? <span>· {radio.tx_power} dBm</span> : null}
              </div>
            ))}
            {wifi.radios.length === 0 ? (
              <p className="text-xs text-muted-foreground">No radios detected.</p>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}