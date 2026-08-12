"use client";

import { useCallback, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { countOnlineLanClients } from "@/lib/clients";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type {
  DhcpLease,
  FirewallZone,
  NetworkInterface,
  NetworkStatus,
  RouteEntry,
  Source,
} from "@/lib/dashboard";
import type { NetworkAction } from "@/lib/router-management";

export type NetworkNotice = { tone: "success" | "danger"; message: string };

export type NetworkDataResult = {
  interfaces: NetworkInterface[];
  networkStatus: NetworkStatus | null;
  routing: RouteEntry[];
  leases: DhcpLease[];
  lanClientCount: number | null;
  zones: FirewallZone[];
  dhcpEnabled: boolean;
  hostname: string;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
  busy: boolean;
  notice: NetworkNotice | null;
  dismissNotice: () => void;
  runInterfaceAction: (action: NetworkAction, section: string) => Promise<void>;
  reloadNetwork: () => Promise<void>;
  restartNetwork: () => Promise<void>;
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function jobMessage(job: { status: string; result: unknown; message: string }, fallback: string): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message ?? fallback;
}

/**
 * Live network state plus real interface/WAN management for the router.
 *
 * Consumes the polling dashboard snapshot for interfaces, the default
 * gateway/DNS, routes and DHCP lease view, and exposes the management actions
 * (enable/disable/restart an interface, renew/release a lease, reload/restart
 * the network) through the backend management job service over SSH. Successful
 * changes trigger an immediate refetch so the UI tracks reality.
 */
export function useNetwork(): NetworkDataResult {
  const { update, status, loading, error, refetch } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<NetworkNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const network = snapshot?.network ?? [];
  const networkStatus = snapshot?.network_status ?? null;
  const routing = snapshot?.routing ?? [];
  const leases = snapshot?.dhcp?.leases ?? [];
  const zones = snapshot?.firewall?.zones ?? [];
  const dhcpEnabled = snapshot?.dhcp?.enabled ?? false;
  const hostname = snapshot?.kernel.hostname ?? "";
  const updatedAt = update?.sent_at ?? null;
  const lanClientCount = countOnlineLanClients(snapshot, updatedAt);

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const announce = useCallback((tone: NetworkNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const runInterfaceAction = useCallback(
    async (action: NetworkAction, section: string) => {
      setNotice(null);
      try {
        const job = await runner.runNetwork(action, section);
        announce(
          job.status === "succeeded" ? "success" : "danger",
          jobMessage(job, "Network operation completed."),
        );
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetch],
  );

  const reloadNetwork = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("reload-network");
      announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "Network reloaded."));
      if (job.status === "succeeded") {
        refetch();
      }
    } catch (e) {
      announce("danger", message(e));
    }
  }, [runner, announce, refetch]);

  const restartNetwork = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("restart-network");
      announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "Network restarted."));
      if (job.status === "succeeded") {
        refetch();
      }
    } catch (e) {
      announce("danger", message(e));
    }
  }, [runner, announce, refetch]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    interfaces: network,
    networkStatus,
    routing,
    leases,
    lanClientCount,
    zones,
    dhcpEnabled,
    hostname,
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
    dismissNotice,
    runInterfaceAction,
    reloadNetwork,
    restartNetwork,
  };
}