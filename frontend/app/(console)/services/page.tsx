"use client";

import { ServerCog } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { ServiceActions } from "@/components/services/service-actions";
import { ServiceDetails } from "@/components/services/service-details";
import { ServicesCritical } from "@/components/services/services-critical";
import { ServicesEnabled } from "@/components/services/services-enabled";
import { ServicesOperations } from "@/components/services/services-operations";
import { ServicesOverview } from "@/components/services/services-overview";
import { ServicesRunning } from "@/components/services/services-running";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useServices } from "@/hooks/use-services";
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

export default function ServicesPage() {
  const servicesHook = useServices();
  const {
    services,
    criticalServices,
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
  } = servicesHook;

  const [routers, setRouters] = useState<SavedRouter[] | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const detailsRef = useRef<HTMLDivElement>(null);

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

  const names = useMemo(
    () => new Set((services?.services ?? []).map((entry) => entry.name)),
    [services],
  );

  const effectiveSelected = useMemo(() => {
    if (services === null) return null;
    if (selected !== null && names.has(selected)) return selected;
    const running = services.services.find((entry) => entry.running);
    return (running ?? services.services[0])?.name ?? null;
  }, [services, selected, names]);

  const selectedService = useMemo(
    () =>
      services?.services.find((entry) => entry.name === effectiveSelected) ?? null,
    [services, effectiveSelected],
  );

  const selectAndScroll = useCallback((name: string) => {
    setSelected(name);
    detailsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
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
          <ServerCog className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to start, stop, restart and configure
            system services — no demo data.
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
              <ServerCog className="size-6 text-muted-foreground" aria-hidden />
              Services
            </h1>
            <p className="text-sm text-muted-foreground">
              OpenWrt service management on{" "}
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
            Failed to load live service data: {widgetError}
          </p>
        ) : null}

        {services === null && !loading ? (
          <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
            No service inventory could be read from the router.
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

      <ServicesOperations job={job} busy={busy} />

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Overview</h2>
        </div>
        <ServicesOverview services={services} />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Service state</h2>
        </div>
        <ServicesRunning
          services={services}
          selectedName={effectiveSelected}
          onSelect={selectAndScroll}
        />
        <ServicesEnabled
          services={services}
          selectedName={effectiveSelected}
          onSelect={selectAndScroll}
        />
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Health</h2>
        </div>
        <ServicesCritical services={criticalServices} loading={loading} />
      </section>

      <section ref={detailsRef} className="scroll-mt-4 space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Manage</h2>
        </div>
        <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
          <ServiceDetails service={selectedService} ubus={services?.ubus ?? false} />
          <ServiceActions service={selectedService} busy={busy} onAction={runAction} />
        </div>
      </section>
    </div>
  );
}