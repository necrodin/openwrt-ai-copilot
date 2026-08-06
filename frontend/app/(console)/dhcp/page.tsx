"use client";

import { BookOpenText } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { DhcpActions } from "@/components/dhcp/dhcp-actions";
import { DhcpLeases } from "@/components/dhcp/dhcp-leases";
import { DhcpOverview } from "@/components/dhcp/dhcp-overview";
import { DhcpStaticLeases } from "@/components/dhcp/dhcp-static";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useDhcp } from "@/hooks/use-dhcp";
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

export default function DhcpPage() {
  const {
    dhcp,
    status,
    loading,
    error,
    connected,
    source,
    routerLabel,
    updatedAt,
    busy,
    notice,
    setEnabled,
    reload,
    restart,
    addHost,
    editHost,
    deleteHost,
    toggleHost,
  } = useDhcp();

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
          <BookOpenText className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to manage DHCP leases — no demo data.
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

  return (
    <div className="min-w-0 flex-1 space-y-4 p-4 lg:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="text-2xl font-bold tracking-tight">DHCP</h1>
            <p className="text-sm text-muted-foreground">
              Server and leases on{" "}
              <span className="font-medium text-foreground">{routerLabel}</span>
              {" · "}
              {updatedAt
                ? `last updated ${formatClock(updatedAt)}`
                : "waiting for data…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={conn.label} tone={conn.tone} dot />
            {source ? (
              <StatusBadge label={sourceLabel(source)} tone="neutral" />
            ) : null}
            {dhcp ? (
              <StatusBadge
                label={dhcp.enabled ? "Active" : "Disabled"}
                tone={dhcp.enabled ? "success" : "danger"}
              />
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

      {widgetLoading ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : !dhcp ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : (
        <div className="space-y-8">
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
              <h2 className="text-lg font-semibold">Server Overview</h2>
            </div>
            <DhcpOverview dhcp={dhcp} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Active Leases</h2>
              <span className="text-xs text-muted-foreground">
                {dhcp.leases.length} active
              </span>
            </div>
            <DhcpLeases leases={dhcp.leases} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Static Leases</h2>
              <span className="text-xs text-muted-foreground">
                {dhcp.static_leases.length} configured
              </span>
            </div>
            <DhcpStaticLeases
              staticLeases={dhcp.static_leases}
              busy={busy}
              onToggle={toggleHost}
              onSave={(input) => (input.section ? editHost(input) : addHost(input))}
              onDelete={deleteHost}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Actions</h2>
            </div>
            <DhcpActions
              enabled={dhcp.enabled}
              busy={busy}
              onSetEnabled={setEnabled}
              onReload={reload}
              onRestart={restart}
            />
          </section>
        </div>
      )}
    </div>
  );
}