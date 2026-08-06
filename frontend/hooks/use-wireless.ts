"use client";

import { useCallback, useMemo, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { buildClients } from "@/lib/clients";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source, WifiClient, WifiInfo } from "@/lib/dashboard";

export type WirelessNotice = { tone: "success" | "danger"; message: string };

/**
 * A live associated station with the hostname/IP merged from the shared
 * snapshot (DHCP/ARP) whenever the MAC can be matched.
 */
export type WirelessStation = {
  mac: string;
  hostname: string | null;
  ip: string | null;
  ssid: string | null;
  signal_dbm: number | null;
  noise: number | null;
  rx_rate: number | null;
  tx_rate: number | null;
  tx_bytes: number | null;
  rx_bytes: number | null;
  connected_time: number | null;
  interface: string | null;
};

export type WirelessDataResult = {
  wifi: WifiInfo | null;
  stations: WirelessStation[];
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
  busy: boolean;
  notice: WirelessNotice | null;
  toggleSsid: (section: string, enabled: boolean) => Promise<void>;
  reload: () => Promise<void>;
  restart: () => Promise<void>;
  dismissNotice: () => void;
};

function normalizeMac(mac: string): string {
  return mac.toLowerCase().replace(/[:-]/g, "");
}

/**
 * Wireless configuration and management for the live dashboard.
 *
 * Consumes the polling dashboard snapshot for radios/SSIDs/stations and exposes
 * the real management actions (enable/disable an SSID, reload or restart the
 * wireless service) through the backend management job service over SSH. A
 * successful change triggers an immediate refetch so the UI picks up the new
 * state instead of waiting for the next poll.
 */
export function useWireless(): WirelessDataResult {
  const { update, status, loading, error, refetch } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<WirelessNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const wifi = snapshot?.wifi ?? null;
  const updatedAt = update?.sent_at ?? null;

  const clientsByMac = useMemo(() => {
    const index = new Map<string, { hostname: string | null; ip: string | null }>();
    for (const client of buildClients(snapshot, updatedAt)) {
      if (client.mac) {
        index.set(normalizeMac(client.mac), {
          hostname: client.hostname,
          ip: client.ipv4 ?? client.ipv6,
        });
      }
    }
    return index;
  }, [snapshot, updatedAt]);

  const stations = useMemo<WirelessStation[]>(() => {
    if (!wifi) {
      return [];
    }
    return wifi.clients.map((client: WifiClient) => {
      const merged = client.mac ? clientsByMac.get(normalizeMac(client.mac)) : undefined;
      return {
        mac: client.mac,
        hostname: merged?.hostname ?? null,
        ip: merged?.ip ?? null,
        ssid: client.ssid,
        signal_dbm: client.signal_dbm,
        noise: client.noise,
        rx_rate: client.rx_rate,
        tx_rate: client.tx_rate,
        tx_bytes: client.tx_bytes,
        rx_bytes: client.rx_bytes,
        connected_time: client.connected_time ?? (client.connected_minutes ?? 0) * 60,
        interface: client.interface,
      };
    });
  }, [wifi, clientsByMac]);

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const toggleSsid = useCallback(
    async (section: string, enabled: boolean) => {
      setNotice(null);
      const actionLabel = enabled ? "Enable" : "Disable";
      try {
        const job = await runner.runWirelessToggle(section, enabled);
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
        setNotice({
          tone: "danger",
          message: e instanceof Error ? e.message : String(e),
        });
      }
    },
    [runner, refetch],
  );

  const reload = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("reload-wireless");
      setNotice({
        tone: job.status === "succeeded" ? "success" : "danger",
        message:
          (job.result as { message?: string } | null)?.message ??
          job.message ??
          "Wireless reloaded.",
      });
    } catch (e) {
      setNotice({
        tone: "danger",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [runner]);

  const restart = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("restart-wifi");
      setNotice({
        tone: job.status === "succeeded" ? "success" : "danger",
        message:
          (job.result as { message?: string } | null)?.message ??
          job.message ??
          "Wireless restarted.",
      });
    } catch (e) {
      setNotice({
        tone: "danger",
        message: e instanceof Error ? e.message : String(e),
      });
    }
  }, [runner]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    wifi,
    stations,
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
    toggleSsid,
    reload,
    restart,
    dismissNotice,
  };
}