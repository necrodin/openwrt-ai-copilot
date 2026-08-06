"use client";

import { useCallback, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { FirewallInfo, Source } from "@/lib/dashboard";

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
  notice: FirewallNotice | null;
  toggleRule: (section: string, enabled: boolean) => Promise<void>;
  reload: () => Promise<void>;
  dismissNotice: () => void;
};

/**
 * Firewall configuration and management for the live dashboard.
 *
 * Pulls the current firewall snapshot from the polling dashboard feed and
 * exposes the real management actions (enable/disable a rule section and reload
 * the firewall) which are executed through the backend management job service
 * over SSH. A successful change triggers an immediate refetch so the UI picks
 * up the new state instead of waiting for the next poll.
 */
export function useFirewall(): FirewallDataResult {
  const { update, status, loading, error, refetch } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<FirewallNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const firewall = snapshot?.firewall ?? null;
  const updatedAt = update?.sent_at ?? null;

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const toggleRule = useCallback(
    async (section: string, enabled: boolean) => {
      setNotice(null);
      const actionLabel = enabled ? "Enable" : "Disable";
      try {
        const job = await runner.runFirewallToggle(section, enabled);
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
      const job = await runner.runAction("reload-firewall");
      setNotice({
        tone: job.status === "succeeded" ? "success" : "danger",
        message:
          (job.result as { message?: string } | null)?.message ??
          job.message ??
          "Firewall reloaded.",
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
    firewall,
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
    toggleRule,
    reload,
    dismissNotice,
  };
}