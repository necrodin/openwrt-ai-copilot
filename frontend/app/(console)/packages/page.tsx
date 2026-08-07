"use client";

import { Package } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { PackageDetails } from "@/components/packages/package-details";
import { PackagesFeeds } from "@/components/packages/packages-feeds";
import { PackagesInstalled } from "@/components/packages/packages-installed";
import { PackagesOperations } from "@/components/packages/packages-operations";
import { PackagesOverview } from "@/components/packages/packages-overview";
import { PackagesSearch } from "@/components/packages/packages-search";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { usePackages } from "@/hooks/use-packages";
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

const ITEMS_PER_PAGE = 25;

export default function PackagesPage() {
  const packagesHook = usePackages();
  const {
    inventory,
    loading,
    error,
    feeds,
    status,
    connected,
    source,
    routerLabel,
    updatedAt,
    busy,
    job,
    notice,
    dismissNotice,
    runAction,
    updateFeeds,
  } = packagesHook;

  const [routers, setRouters] = useState<SavedRouter[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    listConnections()
      .then((data) => {
        if (!cancelled) setRouters(data.routers);
      })
      .catch(() => {
        if (!cancelled) setRouters([]);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const selectedInfo = useMemo(() => {
    if (!selected || !inventory) return null;
    return inventory.packages.find((pkg) => pkg.name === selected) ?? null;
  }, [selected, inventory]);

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
          <Package className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to install, remove, upgrade and search
            packages — no demo data.
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
  const widgetError = !loading && updatedAt === null && error !== null ? error : null;

  return (
    <div className="min-w-0 flex-1 space-y-4 p-4 lg:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <Package className="size-6 text-muted-foreground" aria-hidden />
              Packages
            </h1>
            <p className="text-sm text-muted-foreground">
              Software installation and management on{" "}
              <span className="font-medium text-foreground">{routerLabel}</span>
              {" · "}
              {updatedAt ? `last updated ${formatClock(updatedAt)}` : "waiting for data…"}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge label={conn.label} tone={conn.tone} dot />
            {source ? <StatusBadge label={sourceLabel(source)} tone="neutral" /> : null}
          </div>
        </div>

        {connected === false ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            Device unreachable. Showing the last known state while we retry.
          </p>
        ) : null}

        {widgetError ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            Failed to load live package data: {widgetError}
          </p>
        ) : null}

        {inventory === null && !loading ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            No package inventory could be read from the router. Verify the device
            exposes a supported package manager (apk or opkg).
          </p>
        ) : null}
      </header>

      {notice ? (
        <div className="flex items-center justify-between gap-3">
          <p
            className={
              notice.tone === "success"
                ? "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400"
                : "rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            }
          >
            {notice.message}
          </p>
          <Button variant="ghost" size="sm" onClick={dismissNotice}>
            Dismiss
          </Button>
        </div>
      ) : null}

      <PackagesOperations job={job} busy={busy} />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Overview</h2>
        </div>
        <PackagesOverview inventory={inventory} feeds={feeds} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Package feeds</h2>
          <span className="text-xs text-muted-foreground">Confirmation required</span>
        </div>
        <PackagesFeeds
          feeds={feeds}
          loading={loading}
          error={error}
          busy={busy}
          onUpdate={updateFeeds}
        />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Installed packages</h2>
          <span className="text-xs text-muted-foreground">{ITEMS_PER_PAGE} per page</span>
        </div>
        <PackagesInstalled
          inventory={inventory}
          loading={loading}
          error={error}
          busy={busy}
          selected={selected}
          onSelect={setSelected}
          onAction={runAction}
        />
        {selected ? (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold">Package details</h2>
            <PackageDetails
              name={selected}
              installed={selectedInfo !== null}
              installedVersion={selectedInfo?.version ?? null}
              upgrade={selectedInfo?.upgrade ?? null}
              busy={busy}
              onAction={runAction}
            />
          </div>
        ) : null}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Repository search</h2>
        </div>
        <PackagesSearch busy={busy} onAction={runAction} />
      </section>
    </div>
  );
}