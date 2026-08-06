"use client";

import type { VpnPeer } from "@/hooks/use-vpn";
import { formatBytes, formatDuration } from "@/lib/dashboard-utils";
import { Badge } from "@/components/ui/badge";

type Props = {
  peers: VpnPeer[];
};

function shorten(publicKey: string): string {
  if (publicKey.length <= 12) {
    return publicKey;
  }
  return `${publicKey.slice(0, 8)}…${publicKey.slice(-4)}`;
}

function handshakeLabel(epoch: number | null): string {
  if (epoch == null) {
    return "—";
  }
  const secondsAgo = Math.round(Date.now() / 1000) - epoch;
  if (!Number.isFinite(secondsAgo) || secondsAgo < 0) {
    return formatDuration(epoch < 10_000_000_000 ? epoch : secondsAgo);
  }
  return `${formatDuration(secondsAgo)} ago`;
}

export function VpnPeers({ peers }: Props) {
  if (peers.length === 0) {
    return <p className="text-xs text-muted-foreground">No peers reported.</p>;
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full min-w-[560px] text-left text-sm">
        <thead>
          <tr className="border-b bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
            <th className="px-3 py-2 font-medium">Peer</th>
            <th className="px-3 py-2 font-medium">Endpoint</th>
            <th className="px-3 py-2 font-medium">Allowed IPs</th>
            <th className="px-3 py-2 font-medium">Handshake</th>
            <th className="px-3 py-2 font-medium">Keepalive</th>
            <th className="px-3 py-2 font-medium">RX</th>
            <th className="px-3 py-2 font-medium">TX</th>
          </tr>
        </thead>
        <tbody>
          {peers.map((peer) => (
            <tr key={peer.public_key ?? peer.endpoint ?? "peer"} className="border-b last:border-0">
              <td className="px-3 py-2 font-mono text-xs">
                {peer.public_key ? shorten(peer.public_key) : "—"}
              </td>
              <td className="px-3 py-2 font-mono text-xs">{peer.endpoint ?? "—"}</td>
              <td className="px-3 py-2">
                <div className="flex flex-wrap gap-1">
                  {peer.allowed_ips.length > 0 ? (
                    peer.allowed_ips.map((ip) => (
                      <Badge key={ip} variant="outline" className="font-mono">
                        {ip}
                      </Badge>
                    ))
                  ) : (
                    <span className="text-xs text-muted-foreground">—</span>
                  )}
                </div>
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {handshakeLabel(peer.latest_handshake)}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {peer.persistent_keepalive != null
                  ? `${peer.persistent_keepalive}s`
                  : "—"}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {formatBytes(peer.rx_bytes)}
              </td>
              <td className="px-3 py-2 text-xs text-muted-foreground">
                {formatBytes(peer.tx_bytes)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}