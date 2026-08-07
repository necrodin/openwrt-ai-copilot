"use client";

import { useCallback, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { usePolling } from "@/hooks/use-polling";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source } from "@/lib/dashboard";
import {
  fetchSystemInfo,
  type ManagementJob,
  type SystemConfig,
  type SystemInfo,
} from "@/lib/router-management";

export type SystemNotice = { tone: "success" | "danger"; message: string };

export type SystemDataResult = {
  system: SystemInfo | null;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
busy: boolean;
  job: ManagementJob | null;
  notice: SystemNotice | null;
  dismissNotice: () => void;
  refresh: () => void;
  saveConfig: (config: SystemConfig) => Promise<void>;
  runAction: (action: string) => Promise<void>;
  createBackup: () => Promise<ManagementJob>;
  stageRestore: (file: File) => Promise<ManagementJob>;
  confirmRestore: (jobId: string) => Promise<ManagementJob>;
  downloadArtifact: (job: ManagementJob) => Promise<void>;
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message ?? "Operation completed.";
}

/**
 * System configuration and management for the live router.
 *
 * Pulls the read-only system snapshot over the management API (hostname, time,
 * NTP, firmware, flash, filesystems, board details…) while reusing the tracked
 * management job infrastructure for every mutating operation: saving system
 * settings, syncing/restarting time, backing up and restoring configuration,
 * and the destructive reboot / shutdown / factory reset (each guarded behind an
 * explicit confirm flow).
 */
export function useSystem(): SystemDataResult {
  const { update, status, loading, error } = useDashboardData();
  const runner = useManagementJob();
  const systemPoll = usePolling(fetchSystemInfo, { intervalMs: 10000 });
  const refetchSystem = systemPoll.refetch;
  const [notice, setNotice] = useState<SystemNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const updatedAt = update?.sent_at ?? null;
  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const announce = useCallback((tone: SystemNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const justSaved = useCallback(
    (job: ManagementJob) => {
      announce(job.status === "succeeded" ? "success" : "danger", describe(job));
      if (job.status === "succeeded") {
        refetchSystem();
      }
    },
    [announce, refetchSystem],
  );

  const saveConfig = useCallback(
    async (config: SystemConfig) => {
      setNotice(null);
      try {
        justSaved(await runner.saveSystem(config));
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, justSaved],
  );

  const runAction = useCallback(
    async (action: string) => {
      setNotice(null);
      try {
        justSaved(await runner.runAction(action));
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, justSaved],
  );

  const createBackup = useCallback(
    async () => {
      setNotice(null);
      try {
        const job = await runner.createBackup();
        if (job.status === "failed") {
          announce("danger", describe(job));
        }
        return job;
      } catch (e) {
        announce("danger", message(e));
        throw e;
      }
    },
    [runner, announce],
  );

  const stageRestore = useCallback(
    async (file: File) => {
      setNotice(null);
      try {
        return await runner.stageRestore(file);
      } catch (e) {
        announce("danger", message(e));
        throw e;
      }
    },
    [runner, announce],
  );

  const confirmRestore = useCallback(
    async (jobId: string) => {
      setNotice(null);
      try {
        const job = await runner.confirmRestore(jobId);
        justSaved(job);
        return job;
      } catch (e) {
        announce("danger", message(e));
        throw e;
      }
    },
    [runner, announce, justSaved],
  );

  const downloadArtifact = useCallback(
    async (job: ManagementJob) => {
      setNotice(null);
      try {
        await runner.downloadArtifact(job);
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  const refresh = useCallback(() => {
    refetchSystem();
  }, [refetchSystem]);

  return {
    system: systemPoll.data,
    status,
    loading,
    error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    busy: runner.busy,
    job: runner.job,
    notice,
    dismissNotice,
    refresh,
    saveConfig,
    runAction,
    createBackup,
    stageRestore,
    confirmRestore,
    downloadArtifact,
  };
}