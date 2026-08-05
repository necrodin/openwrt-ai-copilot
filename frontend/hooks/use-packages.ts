"use client";

import { useCallback } from "react";

import { fetchPackages, refreshPackages, type PackageInventory } from "@/lib/router-management";
import { usePolling } from "@/hooks/use-polling";

const DEFAULT_POLL_MS = 60_000;

/**
 * Package inventory from `/router/management/packages`. Polled slowly by
 * default; `refresh()` force-busts the backend TTL cache and reloads.
 */
export function usePackages(intervalMs: number = DEFAULT_POLL_MS) {
  const fetcher = useCallback((signal: AbortSignal) => fetchPackages(false, signal), []);
  const { data, loading, error, refetch } = usePolling<PackageInventory>(fetcher, {
    intervalMs,
  });

  const refresh = useCallback(async () => {
    await refreshPackages();
    refetch();
  }, [refetch]);

  return { inventory: data, loading, error, refresh };
}