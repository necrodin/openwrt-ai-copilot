"use client";

import { useCallback } from "react";

import { fetchManagementLogs, type LogResponse } from "@/lib/router-management";
import { usePolling } from "@/hooks/use-polling";

const DEFAULT_POLL_MS = 8_000;

/**
 * Live system log feed from `/router/management/logs`. Polled every few
 * seconds so the log viewer refreshes on its own; the panel itself decides how
 * to render/clear the streaming buffer.
 */
export function useSystemLogs(intervalMs: number = DEFAULT_POLL_MS) {
  const fetcher = useCallback((signal: AbortSignal) => fetchManagementLogs(500, signal), []);
  return usePolling<LogResponse>(fetcher, { intervalMs });
}