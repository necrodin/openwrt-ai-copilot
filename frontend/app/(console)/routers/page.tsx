"use client";

import {
  Cpu,
  FileText,
  Package,
  Router as RouterIcon,
  ServerCog,
  Settings,
  ShieldCheck,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DiagnosticsChecks } from "@/components/router/diagnostics-checks";
import { ManagementActionsPanel } from "@/components/router/management-actions-panel";
import { RouterOverviewWidget } from "@/components/router/overview-widget";
import { PackagesPanel, type RouterPackage } from "@/components/router/packages-panel";
import { SectionTabs, type SectionTab } from "@/components/router/section-tabs";
import { SystemLogsPanel, type LogEntry } from "@/components/router/system-logs-panel";
import { CpuWidget } from "@/components/dashboard/cpu-widget";
import { DiagnosisWidget } from "@/components/dashboard/diagnosis-widget";
import { HealthScoreWidget } from "@/components/dashboard/health-score-widget";
import { MemoryWidget } from "@/components/dashboard/memory-widget";
import { RecommendationsWidget } from "@/components/dashboard/recommendations-widget";
import { ServicesWidget } from "@/components/dashboard/services-widget";
import { StorageWidget } from "@/components/dashboard/storage-widget";
import { TemperatureWidget } from "@/components/dashboard/temperature-widget";
import { WidgetGrid } from "@/components/dashboard/widget-grid";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useRouterStatus } from "@/hooks/use-router-status";
import { formatClock, sourceLabel, type ConnectionStatus } from "@/lib/dashboard-utils";
import { listConnections, type SavedRouter } from "@/lib/onboarding";

const TABS: SectionTab[] = [
  { id: "overview", label: "Overview", icon: RouterIcon },
  { id: "hardware", label: "Hardware", icon: Cpu },
  { id: "diagnostics", label: "Diagnostics", icon: ShieldCheck },
  { id: "services", label: "Services", icon: ServerCog },
  { id: "packages", label: "Packages", icon: Package },
  { id: "logs", label: "System Logs", icon: FileText },
  { id: "actions", label: "Actions", icon: Settings },
];

function connectionBadge(status: ConnectionStatus): {
  label: string;
  tone: StatusBadgeTone;
} {
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

export default function RoutersPage() {
  const { update, status, loading, error } = useDashboardData();
  const routerStatus = useRouterStatus();

  const snapshot = update?.snapshot ?? null;
  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";
  const hostname = snapshot?.kernel?.hostname ?? null;

  const [routers, setRouters] = useState<SavedRouter[] | null>(null);
  const [activeTab, setActiveTab] = useState<string>("overview");

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
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <Skeleton key={index} className="h-44 w-full rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  if (routers.length === 0) {
    return (
      <div className="mx-auto flex min-h-full w-full max-w-md flex-col items-center justify-center gap-6 p-6 text-center">
        <span className="flex size-12 items-center justify-center rounded-full border bg-muted">
          <RouterIcon className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to open the management console.
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

  const connection = connectionBadge(status);
  const widgetLoading = loading && snapshot === null;
  const widgetError = !loading && snapshot === null && error !== null ? error : null;
  const statusLoading = routerStatus.loading && routerStatus.data === null;
  const statusError =
    !routerStatus.loading && routerStatus.data === null && routerStatus.error !== null
      ? routerStatus.error
      : null;
  const findings = routerStatus.data?.diagnosis ?? [];
  const recommendations = routerStatus.data?.recommendations ?? [];

  const packages = (snapshot?.packages ?? []) as RouterPackage[];
  const logs = (snapshot?.logs as LogEntry[] | null | undefined) ?? [];

  return (
    <div className="min-w-0 flex-1 space-y-4 p-4 lg:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">Router Management</h1>
            <p className="text-sm text-muted-foreground">
              Manage{" "}
              <span className="font-medium text-foreground">{routerLabel}</span>
              {hostname ? ` (${hostname})` : ""}
              {" · "}
              {update?.sent_at
                ? `last updated ${formatClock(update.sent_at)}`
                : "waiting for data…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={connection.label} tone={connection.tone} dot />
            {update ? (
              <StatusBadge label={sourceLabel(update.source)} tone="neutral" />
            ) : null}
          </div>
        </div>

        {update?.connected === false ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            Device unreachable: {update.error ?? "unknown error"}. Showing the
            last known state while we retry.
          </p>
        ) : null}

        {widgetError ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            Failed to load live telemetry: {widgetError}
          </p>
        ) : null}
      </header>

      <SectionTabs tabs={TABS} active={activeTab} onChange={setActiveTab} />

      <main aria-label={`${activeTab} section`}>
        {activeTab === "overview" ? (
          <WidgetGrid className="xl:grid-cols-1">
            <RouterOverviewWidget snapshot={snapshot} loading={widgetLoading} error={widgetError} />
          </WidgetGrid>
        ) : null}

        {activeTab === "hardware" ? (
          <WidgetGrid>
            <CpuWidget cpu={snapshot?.cpu ?? null} loading={widgetLoading} error={widgetError} />
            <MemoryWidget memory={snapshot?.memory ?? null} loading={widgetLoading} error={widgetError} />
            <StorageWidget storage={snapshot?.storage ?? []} loading={widgetLoading} error={widgetError} />
            <TemperatureWidget temperature={snapshot?.temperature ?? []} loading={widgetLoading} error={widgetError} />
          </WidgetGrid>
        ) : null}

        {activeTab === "diagnostics" ? (
          <WidgetGrid>
            <DiagnosticsChecks snapshot={snapshot} loading={widgetLoading} error={widgetError} />
            <HealthScoreWidget snapshot={snapshot} loading={widgetLoading} error={widgetError} />
            <DiagnosisWidget findings={findings} loading={statusLoading} error={statusError} />
            <RecommendationsWidget recommendations={recommendations} loading={statusLoading} error={statusError} />
          </WidgetGrid>
        ) : null}

        {activeTab === "services" ? (
          <WidgetGrid>
            <ServicesWidget services={snapshot?.services ?? []} loading={widgetLoading} error={widgetError} />
          </WidgetGrid>
        ) : null}

        {activeTab === "packages" ? (
          <WidgetGrid className="xl:grid-cols-1">
            <PackagesPanel packages={packages} loading={widgetLoading} error={widgetError} />
          </WidgetGrid>
        ) : null}

        {activeTab === "logs" ? (
          <WidgetGrid className="xl:grid-cols-1">
            <SystemLogsPanel lines={logs} loading={widgetLoading} error={widgetError} />
          </WidgetGrid>
        ) : null}

        {activeTab === "actions" ? (
          <WidgetGrid className="xl:grid-cols-1">
            <ManagementActionsPanel />
          </WidgetGrid>
        ) : null}
      </main>
    </div>
  );
}