"use client";

import { useCallback } from "react";

import { fetchDashboardLatest } from "@/lib/dashboard-api";
import type { DashboardUpdate } from "@/lib/dashboard";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import { usePolling } from "@/hooks/use-polling";

export type DashboardDataResult = {
  update: DashboardUpdate | null;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  refetch: () => void;
};

const DEFAULT_POLL_MS = 5000;

/**
 * Subscribes to the live dashboard stream.
 *
 * Transport is intentionally encapsulated here: today it polls the
 * `/dashboard/latest` REST endpoint; swapping it to the WebSocket feed later
 * (`useDashboardSocket`) requires no changes in any dashboard widget.
 */
export function useDashboardData(
  intervalMs: number = DEFAULT_POLL_MS,
): DashboardDataResult {
  const fetcher = useCallback(
    (signal: AbortSignal) => fetchDashboardLatest(signal),
    [],
  );
  const { data, loading, error, refetch } = usePolling(fetcher, { intervalMs });

  const update = data;
  let status: ConnectionStatus = "connecting";
  if (update !== null) {
    status = update.connected ? "live" : "offline";
  } else if (error !== null) {
    status = "offline";
  }

  return { update, status, loading, error, refetch };
}
