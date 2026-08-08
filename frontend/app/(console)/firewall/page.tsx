"use client";

import { Shield } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { FirewallActions } from "@/components/firewall/firewall-actions";
import { FirewallConfiguration } from "@/components/firewall/firewall-configuration";
import { FirewallForwarding } from "@/components/firewall/firewall-forwarding";
import { FirewallForwards } from "@/components/firewall/firewall-forwards";
import { FirewallNatTable } from "@/components/firewall/firewall-nat";
import { FirewallOverview } from "@/components/firewall/firewall-overview";
import { FirewallRules } from "@/components/firewall/firewall-rules";
import { FirewallZones } from "@/components/firewall/firewall-zones";
import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { useFirewall } from "@/hooks/use-firewall";
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

export default function FirewallPage() {
  const {
    firewall,
    status,
    loading,
    error,
    connected,
    source,
    routerLabel,
    updatedAt,
    busy,
    notice,
    dismissNotice,
    runAction,
  } = useFirewall();

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
          <Shield className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to manage zones, rules, forwards and NAT —
            no demo data.
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
            <h1 className="text-2xl font-bold tracking-tight">Firewall</h1>
            <p className="text-sm text-muted-foreground">
              Zones, rules and forwarding on{" "}
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
            {firewall ? (
              <StatusBadge
                label={`${firewall.counts.zones} zones · ${firewall.counts.rules} rules`}
                tone="neutral"
                dot={false}
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
      ) : !firewall ? (
        <div className="rounded-xl border py-10">
          <EmptyState message="No firewall configuration available yet." />
        </div>
      ) : (
        <div className="space-y-8">
          {notice ? (
            <div className="flex items-center justify-between gap-2">
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

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Overview</h2>
            </div>
            <FirewallOverview firewall={firewall} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Zones</h2>
              <span className="text-xs text-muted-foreground">
                Toggle a zone to allow or block traffic through it
              </span>
            </div>
            <FirewallZones
              zones={firewall.zones}
              busy={busy}
              onToggle={(section, enabled) =>
                runAction(enabled ? "enable-zone" : "disable-zone", section)
              }
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Rules</h2>
              <span className="text-xs text-muted-foreground">
                Enable or disable a rule to apply it live
              </span>
            </div>
            <FirewallRules
              rules={firewall.rules}
              busy={busy}
              onToggle={(section, enabled) =>
                runAction(enabled ? "enable-rule" : "disable-rule", section)
              }
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Port Forwards</h2>
              <span className="text-xs text-muted-foreground">
                {firewall.counts.port_forwards} forwards
              </span>
            </div>
            <FirewallForwards forwards={firewall.port_forwards} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Forwarding</h2>
              <span className="text-xs text-muted-foreground">
                Allow traffic between zones
              </span>
            </div>
            <FirewallForwarding
              forwardings={firewall.forwardings}
              busy={busy}
              onToggle={(section, enabled) =>
                runAction(enabled ? "enable-forwarding" : "disable-forwarding", section)
              }
            />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">NAT</h2>
              <span className="text-xs text-muted-foreground">
                {firewall.counts.nat} rules
              </span>
            </div>
            <FirewallNatTable rules={firewall.nat} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Configuration</h2>
            </div>
            <FirewallConfiguration firewall={firewall} />
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-semibold">Actions</h2>
            </div>
            <FirewallActions firewall={firewall} busy={busy} onAction={runAction} />
          </section>
        </div>
      )}
    </div>
  );
}