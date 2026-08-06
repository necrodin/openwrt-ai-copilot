"use client";

import { Boxes, Lock, Network, ShieldCheck } from "lucide-react";

import type { VpnTunnel } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";

type Props = {
  tunnels: VpnTunnel[];
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

export function VpnOverview({ tunnels }: Props) {
  const upCount = tunnels.filter((tunnel) => tunnel.up).length;
  const peerCount = tunnels.reduce((sum, tunnel) => sum + tunnel.peer_count, 0);
  const kinds = new Set(tunnels.map((tunnel) => tunnel.kind));
  const listening = tunnels.filter((tunnel) => tunnel.listen_port != null);

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <StatCard
        icon={<Lock className="size-5 text-muted-foreground" aria-hidden />}
        label="Tunnels configured"
        value={String(tunnels.length)}
      />
      <StatCard
        icon={<Network className="size-5 text-muted-foreground" aria-hidden />}
        label={upCount === 1 ? "Tunnel up" : "Tunnels up"}
        value={String(upCount)}
      />
      <StatCard
        icon={<ShieldCheck className="size-5 text-muted-foreground" aria-hidden />}
        label="Peers"
        value={String(peerCount)}
      />
      <Card>
        <CardContent className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <Boxes className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0 space-y-1.5">
            {listening.length > 0 ? (
              listening.map((tunnel) => (
                <p key={tunnel.name} className="truncate text-xs text-muted-foreground">
                  <span className="font-medium text-foreground">{tunnel.name}</span>
                  {" · :"}
                  {tunnel.listen_port}
                </p>
              ))
            ) : (
              <p className="text-xs text-muted-foreground">
                No tunnel is listening on this device.
              </p>
            )}
            <p className="text-xs text-muted-foreground">
              {Array.from(kinds).sort().join(", ") || "No technologies"}
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}