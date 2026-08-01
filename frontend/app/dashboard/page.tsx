"use client";

import { Activity } from "lucide-react";
import Link from "next/link";

import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { BandwidthWidget } from "@/components/dashboard/bandwidth-widget";
import { CpuWidget } from "@/components/dashboard/cpu-widget";
import { DevicesWidget } from "@/components/dashboard/devices-widget";
import { FirewallWidget } from "@/components/dashboard/firewall-widget";
import { InternetWidget } from "@/components/dashboard/internet-widget";
import { LanWidget } from "@/components/dashboard/lan-widget";
import { MemoryWidget } from "@/components/dashboard/memory-widget";
import { StorageWidget } from "@/components/dashboard/storage-widget";
import { TemperatureWidget } from "@/components/dashboard/temperature-widget";
import { VpnWidget } from "@/components/dashboard/vpn-widget";
import { WanWidget } from "@/components/dashboard/wan-widget";
import { WirelessWidget } from "@/components/dashboard/wireless-widget";
import { useDashboardSocket } from "@/hooks/use-dashboard-socket";
import {
  formatClock,
  sourceLabel,
  type ConnectionStatus,
} from "@/lib/dashboard-utils";
import { cn } from "@/lib/utils";

function StatusBadge({ status }: { status: ConnectionStatus }) {
  const map: Record<ConnectionStatus, { label: string; variant: "default" | "secondary" | "destructive" }> = {
    live: { label: "Live", variant: "default" },
    connecting: { label: "Connecting", variant: "secondary" },
    reconnecting: { label: "Reconnecting", variant: "destructive" },
    offline: { label: "Offline", variant: "destructive" },
  };
  const config = map[status];
  return <Badge variant={config.variant}>{config.label}</Badge>;
}

function LiveDot({ status }: { status: ConnectionStatus }) {
  return (
    <span
      className={cn(
        "relative flex size-2.5",
        status === "live" && "text-emerald-500",
      )}
      aria-hidden
    >
      <span
        className={cn(
          "absolute inline-flex h-full w-full animate-ping rounded-full bg-current opacity-60",
          status !== "live" && "hidden",
        )}
      />
      <span
        className={cn(
          "relative inline-flex size-2.5 rounded-full bg-current",
          status !== "live" && "bg-muted-foreground",
        )}
      />
    </span>
  );
}

export default function DashboardPage() {
  const { update, status } = useDashboardSocket();
  const snapshot = update?.snapshot ?? null;

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Live view of{" "}
            {snapshot
              ? `${snapshot.meta.model || snapshot.meta.board || "router"}`
              : "the router"}
            {" · "}
            {update ? `last updated ${formatClock(update.sent_at)}` : "waiting for data…"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <LiveDot status={status} />
          <StatusBadge status={status} />
          {update ? (
            <Badge variant="outline">
              {sourceLabel(update.source)}
              {update.device_id ? ` · ${update.device_id}` : ""}
            </Badge>
          ) : null}
        </div>
      </header>

      {update?.connected === false ? (
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700">
          Device unreachable: {update.error ?? "unknown error"}. Showing the last
          known state while we retry.
        </p>
      ) : null}

      {snapshot === null ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 12 }).map((_, index) => (
            <Skeleton key={index} className="h-44 w-full rounded-xl" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          <CpuWidget cpu={snapshot.cpu} />
          <MemoryWidget memory={snapshot.memory} />
          <StorageWidget storage={snapshot.storage} />
          <TemperatureWidget temperature={snapshot.temperature} />
          <WanWidget network={snapshot.network} />
          <LanWidget network={snapshot.network} />
          <FirewallWidget firewall={snapshot.firewall} />
          <VpnWidget vpn={snapshot.vpn} />
          <WirelessWidget wifi={snapshot.wifi} />
          <BandwidthWidget snapshot={snapshot} />
          <DevicesWidget snapshot={snapshot} />
          <InternetWidget snapshot={snapshot} />
        </div>
      )}

      <footer className="flex items-center gap-2 text-sm text-muted-foreground">
        <Link href="/" className="underline underline-offset-4 hover:text-foreground">
          Home
        </Link>
        <span aria-hidden>·</span>
        <span className="inline-flex items-center gap-1">
          <Activity className="size-3.5" aria-hidden />
          Real-time updates over WebSocket
        </span>
      </footer>
    </main>
  );
}
