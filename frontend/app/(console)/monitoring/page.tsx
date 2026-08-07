"use client";

import { Activity } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { MonitoringActions } from "@/components/monitoring/monitoring-actions";
import { MonitoringInterfaces } from "@/components/monitoring/monitoring-interfaces";
import { MonitoringOverview } from "@/components/monitoring/monitoring-overview";
import { MonitoringProcesses } from "@/components/monitoring/monitoring-processes";
import { MonitoringRealtime } from "@/components/monitoring/monitoring-realtime";
import { MonitoringSystem } from "@/components/monitoring/monitoring-system";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useMonitoring } from "@/hooks/use-monitoring";
import { formatClock, sourceLabel, type ConnectionStatus } from "@/lib/dashboard-utils";
import { listConnections, type SavedRouter } from "@/lib/onboarding";

function connectionBadge(status: ConnectionStatus): { label: string; tone: StatusBadgeTone } {
  switch (status) {
    case "live":
      return { label: "Live", tone: "success" };
    case "connecting":
      return { label: "Connecting", tone: "warning" };
    case "reconnecting":
      return { label: "Reconnecting", tone: "warning" };
    case "offline":
      return { label: "Offline", tone: "danger" };
  }
}

export default function MonitoringPage() {
  const monitoring = useMonitoring(5000);
  const {
    snapshot,
    processes,
    history,
    status,
    loading,
    error,
    connected,
    source,
    routerLabel,
    updatedAt,
    interval,
    setInterval,
    busy,
    notice,
    dismissNotice,
    refresh,
    refreshProcesses,
    killProcess,
    restartMonitoring,
  } = monitoring;

  const [routers, setRouters] = useState<SavedRouter[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    listConnections()
      .then((data) => {
        if (!cancelled) {
          setRouters(data.routers);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRouters([]);
        }
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (routers === null) {
    return (
      <div className="mx-auto w-full max-w-7xl space-y-6 p-6">
        <Skeleton className="h-9 w-48" />
        <Skeleton className="h-10 w-full max-w-md" />
        <Skeleton className="h-96 w-full rounded-xl" />
      </div>
    );
  }

  if (routers.length === 0) {
    return (
      <div className="mx-auto flex min-h-full w-full max-w-md flex-col items-center justify-center gap-6 p-6 text-center">
        <span className="flex size-12 items-center justify-center rounded-full border bg-muted">
          <Activity className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to view live CPU, memory, processes and
            the rest of its monitoring data — no demo data.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button asChild>
            <Link href="/onboarding">Connect your router</Link>
          </Button>
          <Button asChild variant="outline">
            <Link href="/">Home</Link>
          </Button>
        </div>
      </div>
    );
  }

  const conn = connectionBadge(status);
  const widgetLoading = loading && updatedAt === null;
  const widgetError = !loading && updatedAt === null && error !== null ? error : null;
  const dataReady = snapshot !== null;

  return (
    <div className="min-w-0 flex-1 space-y-4 p-4 lg:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <Activity className="size-6 text-muted-foreground" aria-hidden />
              Monitoring
            </h1>
            <p className="text-sm text-muted-foreground">
              Live system activity on{" "}
              <span className="font-medium text-foreground">{routerLabel}</span>
              {" · "}
              {updatedAt ? `last updated ${formatClock(updatedAt)}` : "waiting for data…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={conn.label} tone={conn.tone} dot />
            {source ? (
              <StatusBadge label={sourceLabel(source)} tone="neutral" />
            ) : null}
          </div>
        </div>

        {connected === false ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            Device unreachable. Showing the last known state while we retry.
          </p>
        ) : null}

        {widgetError ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            Failed to load live telemetry: {widgetError}
          </p>
        ) : null}
      </header>

      {notice ? (
        <p
          className={
            notice.tone === "success"
              ? "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400"
              : "rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
          }
        >
          {notice.message}
        </p>
      ) : null}

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Actions</h2>
        </div>
        <MonitoringActions
          busy={busy}
          notice={notice}
          onRefresh={refresh}
          onRestart={restartMonitoring}
          onDismissNotice={dismissNotice}
        />
      </section>

      {widgetLoading || !dataReady ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : (
        <div className="space-y-8">
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Overview</h2>
            </div>
            <MonitoringOverview snapshot={snapshot} />
          </section>

          <section className="space-y-3">
            <MonitoringRealtime
              cpu={history.cpu}
              mem={history.mem}
              rx={history.rx}
              tx={history.tx}
              cpuPercent={snapshot.cpu?.usage_percent ?? null}
              memPercent={
                snapshot.memory && snapshot.memory.total_kb > 0
                  ? (snapshot.memory.used_kb / snapshot.memory.total_kb) * 100
                  : null
              }
              load={
                snapshot.cpu
                  ? `${snapshot.cpu.load_1.toFixed(2)} / ${snapshot.cpu.load_5.toFixed(2)} / ${snapshot.cpu.load_15.toFixed(2)}`
                  : null
              }
              interval={interval}
              onIntervalChange={setInterval}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Processes</h2>
            </div>
            <MonitoringProcesses
              processes={processes}
              loading={false}
              error={null}
              onRefresh={refreshProcesses}
              onKill={killProcess}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Interfaces</h2>
            </div>
            <MonitoringInterfaces interfaces={snapshot.network} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">System</h2>
            </div>
            <MonitoringSystem snapshot={snapshot} />
          </section>
        </div>
      )}
    </div>
  );
}