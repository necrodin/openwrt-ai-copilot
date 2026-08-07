"use client";

import { useCallback, useState } from "react";

import {
  fetchPackageFeeds,
  refreshPackages,
  fetchPackages,
  type PackageFeed,
  type PackageFeeds,
  type PackageInventory,
  type PackageManager,
} from "@/lib/router-management";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source } from "@/lib/dashboard";
import type { ManagementJob } from "@/lib/router-management";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { usePolling } from "@/hooks/use-polling";

const DEFAULT_POLL_MS = 60_000;
const FEED_POLL_MS = 30_000;

export type PackageActionKind = "install" | "remove" | "upgrade" | "reinstall";
export type PackagesNotice = { tone: "success" | "danger"; message: string };

export type PackagesDataResult = {
  inventory: PackageInventory | null;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  feeds: PackageFeeds | null;
  manager: PackageManager;
  status: ConnectionStatus;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  busy: boolean;
  job: ManagementJob | null;
  notice: PackagesNotice | null;
  dismissNotice: () => void;
  runAction: (action: PackageActionKind, name: string) => Promise<void>;
  updateFeeds: () => Promise<void>;
};

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Package management for the live router.
 *
 * Polls the real package inventory (name/version/upgrade/size/arch and upgrade
 * availability) plus the configured feeds, and drives every mutating operation
 * (install / remove / upgrade / reinstall / update feeds) through the tracked
 * management job framework. After a successful mutation the backend busts its
 * cache and the next poll reflects the change.
 */
export function usePackages(): PackagesDataResult {
  const inventoryPoll = usePolling<PackageInventory>(
    useCallback((signal) => fetchPackages(false, signal), []),
    { intervalMs: DEFAULT_POLL_MS },
  );
  const feedsPoll = usePolling<PackageFeeds>(
    useCallback((signal) => fetchPackageFeeds(signal), []),
    { intervalMs: FEED_POLL_MS },
  );
  const { update, status } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<PackagesNotice | null>(null);

  const inventory = inventoryPoll.data;
  const feeds = feedsPoll.data;
  const updatedAt = update?.sent_at ?? null;
  const routerLabel = update?.snapshot
    ? update.snapshot.meta.model || update.snapshot.meta.board || "router"
    : "router";

  const refetchInventory = inventoryPoll.refetch;
  const refetchFeeds = feedsPoll.refetch;

  const refresh = useCallback(async () => {
    await refreshPackages();
    refetchInventory();
    refetchFeeds();
  }, [refetchInventory, refetchFeeds]);

  const announce = useCallback((tone: PackagesNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const runAction = useCallback(
    async (action: PackageActionKind, name: string) => {
      setNotice(null);
      try {
        const job = await runner.runPackage(action, name);
        announce(
          job.status === "succeeded" ? "success" : "danger",
          describe(job),
        );
        if (job.status === "succeeded") {
          refetchInventory();
          refetchFeeds();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetchInventory, refetchFeeds],
  );

  const updateFeeds = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runPackage("update-feeds");
      announce(job.status === "succeeded" ? "success" : "danger", describe(job));
      if (job.status === "succeeded") {
        refetchInventory();
        refetchFeeds();
      }
    } catch (e) {
      announce("danger", message(e));
    }
  }, [runner, announce, refetchInventory, refetchFeeds]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    inventory,
    loading: inventoryPoll.loading,
    error: inventoryPoll.error,
    refresh,
    feeds,
    manager: inventory?.manager ?? feeds?.manager ?? "unknown",
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
    updateFeeds,
  };
}

export type { PackageFeed, PackageFeeds };