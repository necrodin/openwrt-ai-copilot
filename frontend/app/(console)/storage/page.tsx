"use client";

import { HardDrive } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { StorageDevices } from "@/components/storage/storage-devices";
import { StorageMounts } from "@/components/storage/storage-mounts";
import { StorageOperations } from "@/components/storage/storage-operations";
import { StorageOverview } from "@/components/storage/storage-overview";
import { StorageUsb } from "@/components/storage/storage-usb";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useStorage } from "@/hooks/use-storage";
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

export default function StoragePage() {
  const storageHook = useStorage();
  const {
    storage,
    status,
    loading,
    error,
    connected,
    source,
    routerLabel,
    updatedAt,
    busy,
    job,
    notice,
    dismissNotice,
    runAction,
  } = storageHook;

  const [routers, setRouters] = useState<SavedRouter[] | null>(null);

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
          <HardDrive className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to manage disks, filesystems and USB
            storage — no demo data.
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
              <HardDrive className="size-6 text-muted-foreground" aria-hidden />
              Storage
            </h1>
            <p className="text-sm text-muted-foreground">
              Filesystem and drive management on{" "}
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
            Failed to load live storage data: {widgetError}
          </p>
        ) : null}

        {storage === null && !loading ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            No storage inventory could be read from the router.
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

      <StorageOperations job={job} busy={busy} />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Overview</h2>
        </div>
        <StorageOverview storage={storage} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Block devices</h2>
        </div>
        <StorageDevices storage={storage} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Filesystems</h2>
        </div>
        <StorageMounts storage={storage} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">USB storage</h2>
          <span className="text-xs text-muted-foreground">Confirmation required</span>
        </div>
        <StorageUsb storage={storage} busy={busy} onAction={runAction} />
      </section>
    </div>
  );
}