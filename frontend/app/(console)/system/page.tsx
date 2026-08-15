"use client";

import { Settings2 } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { SystemBackup } from "@/components/system/system-backup";
import { SystemConfig } from "@/components/system/system-config";
import { SystemFirmware } from "@/components/system/system-firmware";
import { SystemInfoSection } from "@/components/system/system-info";
import { SystemOverview } from "@/components/system/system-overview";
import { SystemPower } from "@/components/system/system-power";
import { SystemTime } from "@/components/system/system-time";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useSystem } from "@/hooks/use-system";
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

export default function SystemPage() {
  const systemHook = useSystem();
  const {
    system,
    status,
    loading,
    error,
    connected,
    source,
    routerLabel,
    updatedAt,
    busy,
    notice,
    saveConfig,
    runAction,
    createBackup,
    stageRestore,
    confirmRestore,
    downloadArtifact,
    job,
  } = systemHook;

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
          <Settings2 className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to manage hostname, time, firmware,
            backups and power — no demo data.
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
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <Settings2 className="size-6 text-muted-foreground" aria-hidden />
              System
            </h1>
            <p className="text-sm text-muted-foreground">
              Configuration and management on{" "}
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

      {widgetLoading ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : system === null ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          System information is unavailable right now. Retrying…
        </p>
      ) : (
        <div className="space-y-8">
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Overview</h2>
            </div>
            <SystemOverview system={system} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">System configuration</h2>
            </div>
            <SystemConfig system={system} busy={busy} onSave={saveConfig} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Time</h2>
            </div>
            <SystemTime
              system={system}
              busy={busy}
              onSyncTime={() => void runAction("sync-time")}
              onRestartNtp={() => void runAction("restart-ntp")}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Firmware</h2>
            </div>
            <SystemFirmware system={system} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Backup &amp; Restore</h2>
            </div>
            <SystemBackup
              busy={busy}
              job={job}
              onCreate={createBackup}
              onStage={stageRestore}
              onConfirm={confirmRestore}
              onDownload={downloadArtifact}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Power</h2>
              <span className="text-xs text-muted-foreground">
                Confirmation required
              </span>
            </div>
            <SystemPower
              busy={busy}
              onReboot={() => void runAction("reboot")}
              onShutdown={() => void runAction("shutdown")}
              onFactoryReset={() => void runAction("factory-reset")}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">System information</h2>
            </div>
            <SystemInfoSection system={system} />
          </section>
        </div>
      )}
    </div>
  );
}