"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { usePolling } from "@/hooks/use-polling";
import { useManagementJob } from "@/hooks/use-management-job";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { DeviceSnapshot, Source } from "@/lib/dashboard";
import {
  fetchProcesses,
  killProcess,
  type RouterProcess,
} from "@/lib/router-management";

export type RefreshInterval = 1000 | 3000 | 5000 | 10000 | 15000;

export type MonitoringNotice = { tone: "success" | "danger"; message: string };

export type MonitoringHistory = {
  cpu: number[];
  mem: number[];
  rx: number[];
  tx: number[];
};

export type MonitoringDataResult = {
  snapshot: DeviceSnapshot | null;
  processes: RouterProcess[];
  history: MonitoringHistory;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  interval: RefreshInterval;
  setInterval: (interval: RefreshInterval) => void;
  busy: boolean;
  notice: MonitoringNotice | null;
  dismissNotice: () => void;
  refresh: () => void;
  refreshProcesses: () => void;
  killProcess: (pid: number) => Promise<boolean>;
  restartMonitoring: () => Promise<void>;
};

const HISTORY_LIMIT = 120;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function totalTraffic(snapshot: DeviceSnapshot): { rx: number; tx: number } {
  return snapshot.network.reduce(
    (acc, iface) => ({
      rx: acc.rx + (iface.rx_bytes ?? 0),
      tx: acc.tx + (iface.tx_bytes ?? 0),
    }),
    { rx: 0, tx: 0 },
  );
}

/**
 * Live router monitoring.
 *
 * The dashboard snapshot is polled at the user-selected refresh interval and
 * accumulated into a sliding history of CPU %, memory %, and network
 * throughput samples (computed from real byte-counter deltas — never mock
 * data). Processes come from the management process endpoint over SSH; killing
 * and restarting the monitoring daemon reuse the management job infrastructure.
 */
export function useMonitoring(
  initialInterval: RefreshInterval = 5000,
): MonitoringDataResult {
  const [interval, setIntervalState] = useState<RefreshInterval>(initialInterval);
  const { update, status, loading, error, refetch } = useDashboardData(interval);
  const runner = useManagementJob();
  const [history, setHistory] = useState<MonitoringHistory>({
    cpu: [],
    mem: [],
    rx: [],
    tx: [],
  });
  const previousTraffic = useRef<{ time: number; rx: number; tx: number } | null>(null);
  const lastSequence = useRef<number | null>(null);
  const [notice, setNotice] = useState<MonitoringNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const updatedAt = update?.sent_at ?? null;

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const processes = usePolling(fetchProcesses, { intervalMs: 10000 });
  const refetchProcesses = processes.refetch;

  const pushHistory = useCallback((sample: {
    cpu: number | null;
    mem: number | null;
    rx: number;
    tx: number;
  }) => {
    setHistory((current) => ({
      cpu: [
        ...current.cpu.slice(-(HISTORY_LIMIT - 1)),
        sample.cpu ?? current.cpu.at(-1) ?? 0,
      ],
      mem: [
        ...current.mem.slice(-(HISTORY_LIMIT - 1)),
        sample.mem ?? current.mem.at(-1) ?? 0,
      ],
      rx: [...current.rx.slice(-(HISTORY_LIMIT - 1)), sample.rx],
      tx: [...current.tx.slice(-(HISTORY_LIMIT - 1)), sample.tx],
    }));
  }, []);

  // Fold each new snapshot into the sliding history (CPU %, memory %, and
  // network throughput derived from real byte-counter deltas).
  useEffect(() => {
    if (snapshot === null || update === null) {
      return;
    }
    if (lastSequence.current === update.sequence) {
      return;
    }
    lastSequence.current = update.sequence;

    const cpu = snapshot.cpu?.usage_percent ?? null;
    const mem =
      snapshot.memory && snapshot.memory.total_kb > 0
        ? (snapshot.memory.used_kb / snapshot.memory.total_kb) * 100
        : null;

    const now = Date.now();
    const traffic = totalTraffic(snapshot);
    const prevTraffic = previousTraffic.current;
    previousTraffic.current = { time: now, ...traffic };

    if (prevTraffic !== null && now > prevTraffic.time) {
      const elapsed = (now - prevTraffic.time) / 1000;
      const rxRate = Math.max(0, (traffic.rx - prevTraffic.rx) / elapsed) * 8;
      const txRate = Math.max(0, (traffic.tx - prevTraffic.tx) / elapsed) * 8;
      pushHistory({ cpu, mem, rx: rxRate, tx: txRate });
    } else {
      setHistory((current) => ({
        ...current,
        cpu: [...current.cpu.slice(-(HISTORY_LIMIT - 1)), cpu ?? current.cpu.at(-1) ?? 0],
        mem: [...current.mem.slice(-(HISTORY_LIMIT - 1)), mem ?? current.mem.at(-1) ?? 0],
      }));
    }
  }, [update, snapshot, pushHistory]);

  const announce = useCallback((tone: MonitoringNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const setInterval = useCallback((next: RefreshInterval) => {
    setIntervalState(next);
  }, []);

  const refresh = useCallback(() => {
    setNotice(null);
    refetch();
  }, [refetch]);

  const refreshProcesses = useCallback(() => {
    refetchProcesses();
  }, [refetchProcesses]);

  const killProcessAction = useCallback(
    async (pid: number): Promise<boolean> => {
      setNotice(null);
      try {
        const result = await killProcess(pid);
        announce(result.ok ? "success" : "danger", result.message);
        if (result.ok) {
          refetchProcesses();
        }
        return result.ok;
      } catch (e) {
        announce("danger", message(e));
        return false;
      }
    },
    [announce, refetchProcesses],
  );

  const restartMonitoring = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("restart-monitoring");
      const result = job.result as { message?: string } | null;
      announce(
        job.status === "succeeded" ? "success" : "danger",
        result?.message ?? job.message ?? "Monitoring service restarted.",
      );
    } catch (e) {
      announce("danger", message(e));
    }
  }, [runner, announce]);

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    snapshot,
    processes: processes.data?.processes ?? [],
    history,
    status,
    loading,
    error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    interval,
    setInterval,
    busy: runner.busy,
    notice,
    dismissNotice,
    refresh,
    refreshProcesses,
    killProcess: killProcessAction,
    restartMonitoring,
  };
}