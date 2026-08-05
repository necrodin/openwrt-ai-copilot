"use client";

import { useCallback } from "react";

import { fetchRouterStatus } from "@/lib/dashboard-api";
import { usePolling } from "@/hooks/use-polling";

const DEFAULT_POLL_MS = 60_000;

/**
 * Polls `/router/status` for the derived router snapshot plus diagnosis and
 * recommendations. Polled more slowly than the dashboard feed because the
 * endpoint rebuilds a snapshot over SSH.
 */
export function useRouterStatus(intervalMs: number = DEFAULT_POLL_MS) {
  const fetcher = useCallback(
    (signal: AbortSignal) => fetchRouterStatus(signal),
    [],
  );
  return usePolling(fetcher, { intervalMs });
}
