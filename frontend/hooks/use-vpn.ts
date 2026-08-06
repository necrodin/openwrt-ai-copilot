"use client";

import { useCallback, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source, VpnTunnel } from "@/lib/dashboard";

export type VpnNotice = { tone: "success" | "danger"; message: string };

export type VpnPeer = {
  public_key: string | null;
  endpoint: string | null;
  allowed_ips: string[];
  latest_handshake: number | null;
  persistent_keepalive: number | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
};

export type VpnDataResult = {
  tunnels: VpnTunnel[];
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
  busy: boolean;
  notice: VpnNotice | null;
  toggleInstance: (section: string, enabled: boolean) => Promise<void>;
  reload: () => Promise<void>;
  restart: () => Promise<void>;
  dismissNotice: () => void;
};

export function vpnPeers(tunnel: VpnTunnel): VpnPeer[] {
  const peers = tunnel.detail?.peers;
  if (!Array.isArray(peers)) {
    return [];
  }
  return peers.map((peer) => {
    const entry = peer as Record<string, unknown>;
    const allowed = entry.allowed_ips;
    return {
      public_key: typeof entry.public_key === "string" ? entry.public_key : null,
      endpoint: typeof entry.endpoint === "string" ? entry.endpoint : null,
      allowed_ips: Array.isArray(allowed)
        ? allowed.filter((value): value is string => typeof value === "string")
        : [],
      latest_handshake:
        typeof entry.latest_handshake === "number" ? entry.latest_handshake : null,
      persistent_keepalive:
        typeof entry.persistent_keepalive === "number" ? entry.persistent_keepalive : null,
      rx_bytes: typeof entry.rx_bytes === "number" ? entry.rx_bytes : null,
      tx_bytes: typeof entry.tx_bytes === "number" ? entry.tx_bytes : null,
    };
  });
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * VPN tunnels and management for the live dashboard.
 *
 * Consumes the polling dashboard snapshot for detected tunnels (WireGuard,
 * OpenVPN, Tailscale, IPsec, Zerotier) and exposes the real management actions
 * (enable/disable an OpenVPN instance, reload or restart the OpenVPN service)
 * through the backend management job service over SSH. A successful change
 * triggers an immediate refetch so the UI picks up the new state.
 */
export function useVpn(): VpnDataResult {
  const { update, status, loading, error, refetch } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<VpnNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const tunnels = snapshot?.vpn ?? [];
  const updatedAt = update?.sent_at ?? null;

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const toggleInstance = useCallback(
    async (section: string, enabled: boolean) => {
      setNotice(null);
      const actionLabel = enabled ? "Enable" : "Disable";
      try {
        const job = await runner.runVpnToggle(section, enabled);
        setNotice({
          tone: job.status === "succeeded" ? "success" : "danger",
          message:
            (job.result as { message?: string } | null)?.message ??
            job.message ??
            `${actionLabel} completed.`,
        });
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        setNotice({ tone: "danger", message: message(e) });
      }
    },
    [runner, refetch],
  );

  const reload = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("reload-vpn");
      setNotice({
        tone: job.status === "succeeded" ? "success" : "danger",
        message:
          (job.result as { message?: string } | null)?.message ??
          job.message ??
          "VPN reloaded.",
      });
    } catch (e) {
      setNotice({ tone: "danger", message: message(e) });
    }
  }, [runner]);

  const restart = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("restart-vpn");
      setNotice({
        tone: job.status === "succeeded" ? "success" : "danger",
        message:
          (job.result as { message?: string } | null)?.message ??
          job.message ??
          "VPN restarted.",
      });
    } catch (e) {
      setNotice({ tone: "danger", message: message(e) });
    }
  }, [runner]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    tunnels,
    status,
    loading,
    error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    refetch,
    busy: runner.busy,
    notice,
    toggleInstance,
    reload,
    restart,
    dismissNotice,
  };
}
