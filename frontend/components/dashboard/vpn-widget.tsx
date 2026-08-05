import { Lock } from "lucide-react";

import type { VpnTunnel } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  vpn: VpnTunnel[];
  loading?: boolean;
  error?: string | null;
};

export function VpnWidget({ vpn, loading = false, error = null }: Props) {
  if (vpn.length === 0) {
    return (
      <Widget title="VPN" icon={Lock} loading={loading} error={error}>
        <EmptyState message="No VPN tunnels configured." />
      </Widget>
    );
  }

  return (
    <Widget
      title="VPN"
      icon={Lock}
      subtitle={`${vpn.length} tunnel${vpn.length > 1 ? "s" : ""}`}
      loading={loading}
      error={error}
    >
      <ul className="space-y-2">
        {vpn.map((tunnel) => (
          <li
            key={`${tunnel.kind}:${tunnel.name}`}
            className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
          >
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-sm font-medium">
                <span className="truncate">{tunnel.name}</span>
                <Badge variant="outline">{tunnel.kind}</Badge>
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {tunnel.kind === "wireguard"
                  ? `${tunnel.peer_count} peer${tunnel.peer_count === 1 ? "" : "s"}${
                      tunnel.listen_port ? ` · :${tunnel.listen_port}` : ""
                    }`
                  : tunnel.addresses[0] ?? "OpenVPN tunnel"}
              </p>
            </div>
            <span
              className={cn(
                "shrink-0 rounded-md px-2 py-1 text-xs font-semibold",
                tunnel.up
                  ? "bg-emerald-500 text-white"
                  : "bg-muted text-muted-foreground",
              )}
            >
              {tunnel.up ? "Up" : "Down"}
            </span>
          </li>
        ))}
      </ul>
    </Widget>
  );
}
