"use client";

import { Activity } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

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
  const map: Record<ConnectionStatus, { label: string; variant: "default" | "secondary" | "destructive" | "outline" }> = {
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

interface RouterSystem {
  hostname?: string | null;
  model?: string | null;
  board?: string | null;
  firmware?: string | null;
  kernel?: string | null;
  architecture?: string | null;
  uptime?: string | null;
}

interface RouterCpu {
  usage_percent?: number | null;
  cores?: number | null;
  load_1?: number | null;
  load_5?: number | null;
  load_15?: number | null;
}

interface RouterMemory {
  total_kb?: number | null;
  used_kb?: number | null;
  used_percent?: number | null;
}

interface RouterStorage {
  mountpoint?: string | null;
  device?: string | null;
  filesystem?: string | null;
  total_gb?: number | null;
  used_gb?: number | null;
  use_percent?: number | null;
}

interface RouterSnapshotData {
  system: RouterSystem | null;
  cpu: RouterCpu | null;
  memory: RouterMemory | null;
  storage: RouterStorage[] | null;
}

interface RouterFinding {
  severity: string;
  category: string;
  title: string;
  description: string;
  recommendation: string;
}

interface RouterRecommendation {
  id: string;
  priority: string;
  category: string;
  title: string;
  description: string;
  action: string;
  impact: string;
}

interface RouterStatusResponse {
  snapshot: RouterSnapshotData | null;
  diagnosis: RouterFinding[];
  recommendations: RouterRecommendation[];
}

function formatKb(kb: number | null | undefined): string {
  if (kb == null) return "unknown";
  if (kb >= 1024 * 1024) return `${(kb / (1024 * 1024)).toFixed(1)} GB`;
  if (kb >= 1024) return `${(kb / 1024).toFixed(1)} MB`;
  return `${kb} KB`;
}

function findingVariant(severity: string): "default" | "secondary" | "destructive" | "outline" {
  if (severity === "critical") return "destructive";
  if (severity === "warning") return "outline";
  return "secondary";
}

function priorityVariant(priority: string): "default" | "secondary" | "destructive" | "outline" {
  if (priority === "urgent") return "destructive";
  if (priority === "high") return "outline";
  if (priority === "medium") return "secondary";
  return "default";
}

function RouterStatusPanel({ data }: { data: RouterStatusResponse }) {
  const { snapshot, diagnosis, recommendations } = data;

  if (snapshot === null) {
    return (
      <section className="space-y-2 rounded-xl border p-4">
        <h2 className="text-lg font-semibold tracking-tight">Router Status</h2>
        <p className="text-sm text-muted-foreground">Router unavailable</p>
      </section>
    );
  }

  const system = snapshot.system;
  const cpu = snapshot.cpu;
  const memory = snapshot.memory;
  const storage = snapshot.storage ?? [];
  const hostname = system?.hostname ?? null;

  return (
    <section className="space-y-4 rounded-xl border p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-lg font-semibold tracking-tight">Router Status</h2>
        <Badge variant="default">Online</Badge>
      </div>

      <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2 xl:grid-cols-3">
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Hostname</dt>
          <dd className="font-medium">{hostname ?? "unknown"}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Model</dt>
          <dd className="font-medium">
            {system?.model || system?.board || "unknown"}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Firmware</dt>
          <dd className="font-medium">{system?.firmware ?? "unknown"}</dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Kernel</dt>
          <dd className="font-medium">
            {system?.kernel ?? "unknown"}
            {system?.architecture ? ` (${system.architecture})` : ""}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">CPU</dt>
          <dd className="font-medium">
            {cpu?.usage_percent != null ? `${cpu.usage_percent.toFixed(1)}%` : "N/A"}
            {cpu?.cores != null ? ` · ${cpu.cores} cores` : ""}
          </dd>
        </div>
        <div className="flex justify-between gap-2">
          <dt className="text-muted-foreground">Memory</dt>
          <dd className="font-medium">
            {memory?.used_percent != null ? `${memory.used_percent.toFixed(1)}%` : "N/A"}
            {" · "}
            {formatKb(memory?.used_kb)} / {formatKb(memory?.total_kb)}
          </dd>
        </div>
      </dl>

      {storage.length > 0 ? (
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">Storage</h3>
          <ul className="space-y-1 text-sm">
            {storage.map((mount, index) => (
              <li key={index} className="flex justify-between gap-2">
                <span>
                  {mount.mountpoint ?? "?"} ({mount.filesystem ?? "?"})
                </span>
                <span className="font-medium">
                  {mount.use_percent != null ? `${mount.use_percent.toFixed(1)}%` : "N/A"}
                  {" · "}
                  {mount.used_gb != null ? `${mount.used_gb.toFixed(1)}G` : "?"} /{" "}
                  {mount.total_gb != null ? `${mount.total_gb.toFixed(1)}G` : "?"}
                </span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {diagnosis.length > 0 ? (
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">Diagnosis</h3>
          <ul className="space-y-2 text-sm">
            {diagnosis.map((finding, index) => (
              <li key={index} className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Badge variant={findingVariant(finding.severity)}>
                    {finding.severity}
                  </Badge>
                  <span className="font-medium">{finding.title}</span>
                </div>
                <p className="text-muted-foreground">{finding.description}</p>
                <p className="text-muted-foreground">
                  Recommendation: {finding.recommendation}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {recommendations.length > 0 ? (
        <div className="space-y-1">
          <h3 className="text-sm font-medium text-muted-foreground">Recommendations</h3>
          <ul className="space-y-2 text-sm">
            {recommendations.map((recommendation) => (
              <li key={recommendation.id} className="space-y-0.5">
                <div className="flex items-center gap-2">
                  <Badge variant={priorityVariant(recommendation.priority)}>
                    {recommendation.priority}
                  </Badge>
                  <span className="font-medium">{recommendation.title}</span>
                </div>
                <p className="text-muted-foreground">{recommendation.description}</p>
                <p className="text-muted-foreground">
                  Action: {recommendation.action}
                </p>
                <p className="text-muted-foreground">
                  Impact: {recommendation.impact}
                </p>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </section>
  );
}

export default function DashboardPage() {
  const { update, status } = useDashboardSocket();
  const snapshot = update?.snapshot ?? null;
  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";
  const hostname = snapshot?.kernel?.hostname ?? null;
  const firmware = snapshot?.kernel?.version ?? snapshot?.meta?.firmware ?? null;
  const kernel = snapshot?.kernel?.kernel ?? null;

  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [statusLoading, setStatusLoading] = useState(true);
  const [statusError, setStatusError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function loadRouterStatus() {
      setStatusLoading(true);
      setStatusError(null);
      try {
        const response = await fetch("/api/v1/router/status");
        if (!response.ok) {
          throw new Error(`Router status request failed (${response.status})`);
        }
        const data: RouterStatusResponse = await response.json();
        if (!cancelled) {
          setRouterStatus(data);
        }
      } catch (err) {
        if (!cancelled) {
          setStatusError(err instanceof Error ? err.message : "Failed to load router status");
        }
      } finally {
        if (!cancelled) {
          setStatusLoading(false);
        }
      }
    }
    void loadRouterStatus();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <main className="mx-auto w-full max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div className="space-y-1">
          <h1 className="text-2xl font-bold tracking-tight">Dashboard</h1>
          <p className="text-sm text-muted-foreground">
            Live view of{" "}
            <span className="font-medium text-foreground">{routerLabel}</span>
            {hostname ? ` (${hostname})` : ""}
            {" · "}
            {update ? `last updated ${formatClock(update.sent_at)}` : "waiting for data…"}
          </p>
          {(hostname || firmware || kernel) ? (
            <div className="flex flex-wrap items-center gap-2 pt-1">
              {hostname ? (
                <Badge variant="outline" className="text-xs">{hostname}</Badge>
              ) : null}
              {firmware ? (
                <Badge variant="outline" className="text-xs">Firmware: {firmware}</Badge>
              ) : null}
              {kernel ? (
                <Badge variant="outline" className="text-xs">Kernel: {kernel}</Badge>
              ) : null}
            </div>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <LiveDot status={status} />
          <StatusBadge status={status} />
          {update?.connected !== undefined ? (
            <Badge variant={update.connected ? "default" : "destructive"}>
              {update.connected ? "Online" : "Offline"}
            </Badge>
          ) : null}
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

      {statusLoading ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 3 }).map((_, index) => (
            <Skeleton key={index} className="h-44 w-full rounded-xl" />
          ))}
        </div>
      ) : statusError ? (
        <section className="space-y-2 rounded-xl border border-destructive/40 bg-destructive/10 p-4">
          <h2 className="text-lg font-semibold tracking-tight">Router Status</h2>
          <p className="text-sm text-destructive">
            Failed to load router status: {statusError}
          </p>
        </section>
      ) : routerStatus ? (
        <RouterStatusPanel data={routerStatus} />
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
        <Link href="/chat" className="underline underline-offset-4 hover:text-foreground">
          AI Chat
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
