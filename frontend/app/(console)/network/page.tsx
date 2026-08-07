"use client";

import { BookOpenText, Network } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { NetworkActions } from "@/components/network/network-actions";
import { NetworkBridges } from "@/components/network/network-bridges";
import { NetworkInterfaces } from "@/components/network/network-interfaces";
import { NetworkLan } from "@/components/network/network-lan";
import { NetworkOverview } from "@/components/network/network-overview";
import { NetworkRouting } from "@/components/network/network-routing";
import { NetworkWan } from "@/components/network/network-wan";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useNetwork } from "@/hooks/use-network";
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

export default function NetworkPage() {
  const {
    interfaces: network,
    networkStatus,
    routing,
    leases,
    zones,
    dhcpEnabled,
    hostname,
    status,
    loading,
    error,
    connected,
    source,
    routerLabel,
    updatedAt,
    busy,
    notice,
    runInterfaceAction,
    reloadNetwork,
    restartNetwork,
  } = useNetwork();

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
            Connect your OpenWrt device to manage interfaces and networks — no demo
            data.
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

  const wanIfaces = network.filter((iface) => iface.name.startsWith("wan"));
  const wan = wanIfaces.find((iface) => iface.up) ?? wanIfaces[0] ?? null;
  const lanIfaces = network.filter(
    (iface) => iface.name.startsWith("lan") || iface.device?.startsWith("br-"),
  );
  const lan = lanIfaces.find((iface) => iface.up) ?? lanIfaces[0] ?? null;
  const bridges = network.filter(
    (iface) => iface.is_bridge || (iface.bridge_members?.length ?? 0) > 0,
  );

  return (
    <div className="min-w-0 flex-1 space-y-4 p-4 lg:p-6">
      <header className="space-y-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="space-y-1">
            <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
              <Network className="size-6 text-muted-foreground" aria-hidden />
              Network
            </h1>
            <p className="text-sm text-muted-foreground">
              Interfaces, routing and connectivity on{" "}
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
      ) : network.length === 0 ? (
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
              <h2 className="text-lg font-semibold">Overview</h2>
            </div>
            <NetworkOverview
              interfaces={network}
              networkStatus={networkStatus}
              hostname={hostname}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Interfaces</h2>
              <span className="text-xs text-muted-foreground">
                {network.filter((iface) => iface.up).length} of {network.length} up
              </span>
            </div>
            <NetworkInterfaces
              interfaces={network}
              zones={zones}
              routing={routing}
              dns={networkStatus?.dns ?? []}
              busy={busy}
              onEnable={(section) => runInterfaceAction("interface-enable", section)}
              onDisable={(section) => runInterfaceAction("interface-disable", section)}
              onRestart={(section) => runInterfaceAction("interface-restart", section)}
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Connectivity</h2>
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
              <NetworkWan wan={wan} dns={networkStatus?.dns ?? []} />
              <NetworkLan
                lan={lan}
                leases={leases}
                dhcpEnabled={dhcpEnabled}
              />
            </div>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Bridges</h2>
              <span className="text-xs text-muted-foreground">
                {bridges.length} bridge{bridges.length === 1 ? "" : "s"}
              </span>
            </div>
            <NetworkBridges bridges={bridges} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Routing</h2>
            </div>
            <NetworkRouting routes={routing} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Actions</h2>
            </div>
            <NetworkActions
              interfaces={network}
              busy={busy}
              onRestartInterface={(section) => runInterfaceAction("interface-restart", section)}
              onRenew={(section) => runInterfaceAction("interface-renew", section)}
              onRelease={(section) => runInterfaceAction("interface-release", section)}
              onReload={reloadNetwork}
              onRestart={restartNetwork}
            />
          </section>
        </div>
      )}
    </div>
  );
}