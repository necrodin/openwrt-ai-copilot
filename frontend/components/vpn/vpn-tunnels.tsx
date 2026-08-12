"use client";

import { ChevronDown, ChevronRight, GitPullRequest } from "lucide-react";
import { useState } from "react";

import { vpnPeers } from "@/hooks/use-vpn";
import type { VpnTunnel } from "@/lib/dashboard";
import { formatBytes } from "@/lib/dashboard-utils";
import { tunnelStatus } from "@/lib/vpn-utils";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState } from "@/components/dashboard/widget";
import { VpnPeers } from "@/components/vpn/vpn-peers";

type Props = {
  tunnels: VpnTunnel[];
  busy?: boolean;
  onToggle: (section: string, enabled: boolean) => void;
};

const KIND_LABEL: Record<VpnTunnel["kind"], string> = {
  wireguard: "WireGuard",
  openvpn: "OpenVPN",
  ipsec: "IPsec",
  tailscale: "Tailscale",
  zerotier: "Zerotier",
  other: "VPN",
};

function caption(tunnel: VpnTunnel): string {
  const detail = tunnel.detail ?? {};
  switch (tunnel.kind) {
    case "wireguard":
      return (
        trip([
          tunnel.addresses[0],
          tunnel.listen_port != null ? `listen :${tunnel.listen_port}` : null,
        ]) || "WireGuard tunnel"
      );
    case "openvpn":
      return trip([tunnel.endpoint, tunnel.addresses[0]]) || "OpenVPN tunnel";
    case "tailscale":
      return (
        trip([
          typeof detail.hostname === "string" ? detail.hostname : null,
          tunnel.addresses[0] ?? (typeof detail.ip === "string" ? detail.ip : null),
          typeof detail.tailnet === "string" ? detail.tailnet : null,
          tunnel.version ? `v${tunnel.version}` : null,
        ]) || "Tailscale"
      );
    case "ipsec": {
      const connections = typeof detail.connections === "number" ? detail.connections : null;
      return connections != null
        ? `${connections} connection${connections === 1 ? "" : "s"}`
        : "IPsec";
    }
    case "zerotier": {
      const networks = Array.isArray(detail.networks) ? detail.networks.length : 0;
      return networks > 0 ? `${networks} network${networks === 1 ? "" : "s"}` : "Zerotier";
    }
    default:
      return trip([tunnel.endpoint, tunnel.addresses[0]]) || "VPN tunnel";
  }
}

function trip(parts: Array<string | undefined | null>): string {
  return parts.filter(Boolean).join(" · ");
}

export function VpnTunnels({ tunnels, busy = false, onToggle }: Props) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpanded = (key: string) =>
    setExpanded((prev) => ({ ...prev, [key]: !prev[key] }));

  if (tunnels.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No VPN tunnels detected on this router." />
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {tunnels.map((tunnel) => {
        const name = `${tunnel.kind}:${tunnel.name}`;
        const open = expanded[name];
        const peers = vpnPeers(tunnel);
        const showPeers = tunnel.kind === "wireguard" && peers.length > 0;
        const status = tunnelStatus(tunnel);
        return (
          <li
            key={name}
            className={`rounded-md border px-4 py-3 ${tunnel.up ? "" : "opacity-70"}`}
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="min-w-0 space-y-1">
                <div className="flex flex-wrap items-center gap-2">
                  {showPeers ? (
                    <button
                      type="button"
                      className="flex items-center gap-1 rounded text-muted-foreground transition-colors hover:text-foreground"
                      onClick={() => toggleExpanded(name)}
                      aria-expanded={open}
                      aria-label={`${open ? "Collapse" : "Expand"} peers for ${tunnel.name}`}
                    >
                      {open ? (
                        <ChevronDown className="size-4" aria-hidden />
                      ) : (
                        <ChevronRight className="size-4" aria-hidden />
                      )}
                    </button>
                  ) : (
                    <GitPullRequest className="size-4 text-muted-foreground" aria-hidden />
                  )}
                  <span className="truncate text-sm font-medium">{tunnel.name}</span>
                  <Badge variant="outline">{KIND_LABEL[tunnel.kind]}</Badge>
                  <StatusBadge label={status.label} tone={status.tone} dot />
                </div>
                <p className="text-xs text-muted-foreground">
                  {caption(tunnel)}
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
                {tunnel.rx_bytes != null ? (
                  <span>↓ {formatBytes(tunnel.rx_bytes)}</span>
                ) : null}
                {tunnel.tx_bytes != null ? (
                  <span>↑ {formatBytes(tunnel.tx_bytes)}</span>
                ) : null}
                {tunnel.peer_count > 0 ? (
                  <span>
                    {tunnel.peer_count} peer{tunnel.peer_count === 1 ? "" : "s"}
                  </span>
                ) : null}
                {tunnel.kind === "openvpn" ? (
                  <Button
                    size="sm"
                    variant={tunnel.enabled ? "outline" : "default"}
                    disabled={busy}
                    onClick={() => onToggle(tunnel.name, !tunnel.enabled)}
                  >
                    {tunnel.enabled ? "Disable" : "Enable"}
                  </Button>
                ) : null}
              </div>
            </div>

            {open && showPeers ? (
              <div className="mt-3">
                <VpnPeers peers={peers} />
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}