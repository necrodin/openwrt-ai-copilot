"use client";

import { useCallback, useState } from "react";

import {
  fetchServicesInfo,
  type ManagementJob,
  type ServiceAction,
  type ServicesInfo,
} from "@/lib/router-management";
import type { ServiceInfo, Source } from "@/lib/dashboard";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { usePolling } from "@/hooks/use-polling";

const SERVICES_POLL_MS = 12_000;

export type ServicesNotice = { tone: "success" | "danger"; message: string };

export type ServicesDataResult = {
  services: ServicesInfo | null;
  criticalServices: ServiceInfo[];
  loading: boolean;
  error: string | null;
  refresh: () => void;
  status: ConnectionStatus;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  busy: boolean;
  job: ManagementJob | null;
  notice: ServicesNotice | null;
  dismissNotice: () => void;
  runAction: (action: ServiceAction, name: string) => Promise<void>;
};

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Services management for the live router.
 *
 * Polls the full service inventory (procd/ubus where available, OpenWrt init.d
 * scripts otherwise) and routes start / stop / restart / enable / disable
 * through the tracked management job framework. Critical services come from the
 * dashboard snapshot collector. After a successful mutation the inventory is
 * re-fetched so the UI reflects the new state.
 */
export function useServices(): ServicesDataResult {
  const servicesPoll = usePolling<ServicesInfo>(
    useCallback((signal) => fetchServicesInfo(signal), []),
    { intervalMs: SERVICES_POLL_MS },
  );
  const { update, status } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<ServicesNotice | null>(null);

  const services = servicesPoll.data;
  const updatedAt = update?.sent_at ?? null;
  const routerLabel = update?.snapshot
    ? update.snapshot.meta.model || update.snapshot.meta.board || "router"
    : "router";
  const criticalServices = update?.snapshot?.services ?? [];

  const refetchServices = servicesPoll.refetch;

  const announce = useCallback((tone: ServicesNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const runAction = useCallback(
    async (action: ServiceAction, name: string) => {
      setNotice(null);
      try {
        const job = await runner.runService(action, name);
        announce(
          job.status === "succeeded" ? "success" : "danger",
          describe(job),
        );
        refetchServices();
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetchServices],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    services,
    criticalServices,
    loading: servicesPoll.loading,
    error: servicesPoll.error,
    refresh: servicesPoll.refetch,
    status,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    busy: runner.busy,
    job: runner.job,
    notice,
    dismissNotice,
    runAction,
  };
}