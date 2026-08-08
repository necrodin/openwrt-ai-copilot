"use client";

import { useCallback, useState } from "react";

import {
  fetchStorageInfo,
  type ManagementJob,
  type StorageAction,
  type StorageInfo,
} from "@/lib/router-management";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source } from "@/lib/dashboard";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { usePolling } from "@/hooks/use-polling";

const STORAGE_POLL_MS = 12_000;

export type StorageNotice = { tone: "success" | "danger"; message: string };

export type StorageDataResult = {
  storage: StorageInfo | null;
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
  notice: StorageNotice | null;
  dismissNotice: () => void;
  runAction: (action: StorageAction, target: string) => Promise<void>;
};

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Storage management for the live router.
 *
 * Polls the real block device / filesystem inventory (physical devices, usage
 * by mountpoint, and removable USB storage) and drives mount / unmount /
 * remount operations through the tracked management job framework. After a
 * successful mutation the inventory is re-fetched so the UI reflects the new
 * mount state.
 */
export function useStorage(): StorageDataResult {
  const storagePoll = usePolling<StorageInfo>(
    useCallback((signal) => fetchStorageInfo(signal), []),
    { intervalMs: STORAGE_POLL_MS },
  );
  const { update, status } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<StorageNotice | null>(null);

  const storage = storagePoll.data;
  const updatedAt = update?.sent_at ?? null;
  const routerLabel = update?.snapshot
    ? update.snapshot.meta.model || update.snapshot.meta.board || "router"
    : "router";

  const refetchStorage = storagePoll.refetch;

  const announce = useCallback((tone: StorageNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const runAction = useCallback(
    async (action: StorageAction, target: string) => {
      setNotice(null);
      try {
        const job = await runner.runStorage(action, target);
        announce(
          job.status === "succeeded" ? "success" : "danger",
          describe(job),
        );
        refetchStorage();
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetchStorage],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    storage,
    loading: storagePoll.loading,
    error: storagePoll.error,
    refresh: storagePoll.refetch,
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