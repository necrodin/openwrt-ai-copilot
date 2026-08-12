"use client";

import { useCallback, useMemo, useState } from "react";

import {
  fetchFirewallInfo,
  type FirewallAction,
  type FirewallInfo,
  type ManagementJob,
} from "@/lib/router-management";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { usePolling } from "@/hooks/use-polling";
import { mergeZoneNetworks, sanitizeVersion } from "@/lib/firewall-utils";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source } from "@/lib/dashboard";

const FIREWALL_POLL_MS = 10_000;

export type FirewallNotice = { tone: "success" | "danger"; message: string };

export type FirewallDataResult = {
  firewall: FirewallInfo | null;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
  busy: boolean;
  job: ManagementJob | null;
  notice: FirewallNotice | null;
  dismissNotice: () => void;
  runAction: (action: FirewallAction, section?: string) => Promise<void>;
};

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Firewall configuration and management.
 *
 * Polls the management API for the live UCI firewall configuration and routes
 * every mutation (restart, reload, enable/disable service, per-section rule /
 * zone / forwarding toggles) through the tracked management job framework.
 * After a successful change the inventory is re-fetched so the UI reflects the
 * new state immediately.
 */
export function useFirewall(): FirewallDataResult {
  const firewallPoll = usePolling<FirewallInfo>(
    useCallback((signal) => fetchFirewallInfo(signal), []),
    { intervalMs: FIREWALL_POLL_MS },
  );
  const { update, status } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<FirewallNotice | null>(null);

  const snapshot = update?.snapshot;
  const firewall = useMemo<FirewallInfo | null>(() => {
    if (!firewallPoll.data) {
      return null;
    }
    const snapshotZones = snapshot?.firewall?.zones ?? [];
    return {
      ...firewallPoll.data,
      zones: mergeZoneNetworks(firewallPoll.data.zones, snapshotZones),
      version: sanitizeVersion(firewallPoll.data.version),
    };
  }, [firewallPoll.data, snapshot]);
  const updatedAt = firewall?.generated_at ?? null;
  const routerLabel = update?.snapshot
    ? update.snapshot.meta.model || update.snapshot.meta.board || "router"
    : "router";

  const refetchFirewall = firewallPoll.refetch;

  const announce = useCallback((tone: FirewallNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const runAction = useCallback(
    async (action: FirewallAction, section?: string) => {
      setNotice(null);
      try {
        const job = await runner.runFirewall(action, section);
        announce(job.status === "succeeded" ? "success" : "danger", describe(job));
        if (job.status === "succeeded") {
          refetchFirewall();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetchFirewall],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    firewall,
    status,
    loading: firewallPoll.loading,
    error: firewallPoll.error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    refetch: firewallPoll.refetch,
    busy: runner.busy,
    job: runner.job,
    notice,
    dismissNotice,
    runAction,
  };
}