"use client";

import { MonitorSmartphone, Search, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { ClientDetails } from "@/components/clients/client-details";
import { ClientTable } from "@/components/clients/client-table";
import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge, type StatusBadgeTone } from "@/components/ui/status-badge";
import { getStoredSession } from "@/lib/auth";
import { useClientLabels } from "@/hooks/use-client-labels";
import { useClients } from "@/hooks/use-clients";
import {
  applyClientLabels,
  filterClients,
  sortClients,
  type ClientSortKey,
} from "@/lib/clients";
import type { ClientConnection, ClientMedium } from "@/lib/clients";
import { formatClock, sourceLabel, type ConnectionStatus } from "@/lib/dashboard-utils";
import { listConnections, type SavedRouter } from "@/lib/onboarding";
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

const CONNECTION_OPTIONS: { value: ClientConnection | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "online", label: "Online" },
  { value: "offline", label: "Offline" },
];

const MEDIUM_OPTIONS: { value: ClientMedium | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "wired", label: "Wired" },
  { value: "wireless", label: "Wireless" },
];

export default function ClientsPage() {
  const { clients, status, loading, error, connected, source, routerLabel, updatedAt } =
    useClients();
  const { labels, save: saveLabel, remove: removeLabel } = useClientLabels();

  const [routers, setRouters] = useState<SavedRouter[] | null>(null);
  const [search, setSearch] = useState("");
  const [connection, setConnection] = useState<ClientConnection | "all">("all");
  const [medium, setMedium] = useState<ClientMedium | "all">("all");
  const [sortKey, setSortKey] = useState<ClientSortKey>("name");
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const canEdit = getStoredSession()?.role === "admin";
  const labeledClients = useMemo(
    () => applyClientLabels(clients, labels),
    [clients, labels],
  );

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

  const visible = useMemo(
    () =>
      sortClients(filterClients(labeledClients, { search, connection, medium }), sortKey),
    [labeledClients, search, connection, medium, sortKey],
  );

  const selectedClient =
    labeledClients.find((client) => client.id === selectedId) ?? null;
  const onlineCount = labeledClients.filter((client) => client.online).length;
  const wirelessCount = labeledClients.filter((client) => client.medium === "wireless").length;

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
          <MonitorSmartphone className="size-6 text-muted-foreground" aria-hidden />
        </span>
        <div className="space-y-2">
          <h1 className="text-2xl font-bold tracking-tight">No router connected</h1>
          <p className="text-sm text-muted-foreground">
            Connect your OpenWrt device to see every device on the network — no
            demo data.
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
            <h1 className="text-2xl font-bold tracking-tight">Clients</h1>
            <p className="text-sm text-muted-foreground">
              Every device on{" "}
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
            <StatusBadge
              label={`${clients.length} devices`}
              tone="neutral"
              dot={false}
            />
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

      <div className="space-y-3">
        <div className="flex flex-col gap-3 md:flex-row md:items-center">
          <div className="relative w-full md:max-w-sm">
            <Search
              className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              type="search"
              placeholder="Search label, hostname, IP, MAC, interface…"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              className="pl-9 pr-8"
              aria-label="Search clients"
            />
            {search ? (
              <Button
                type="button"
                variant="ghost"
                size="icon"
                className="absolute top-0 right-0 size-9"
                onClick={() => setSearch("")}
                aria-label="Clear search"
              >
                <X className="size-4" aria-hidden />
              </Button>
            ) : null}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Status</span>
            {CONNECTION_OPTIONS.map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={connection === option.value ? "default" : "outline"}
                onClick={() => setConnection(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">Connection</span>
            {MEDIUM_OPTIONS.map((option) => (
              <Button
                key={option.value}
                type="button"
                size="sm"
                variant={medium === option.value ? "default" : "outline"}
                onClick={() => setMedium(option.value)}
              >
                {option.label}
              </Button>
            ))}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
          <span>
            <span className="font-semibold text-foreground">{visible.length}</span>{" "}
            shown of {clients.length}
          </span>
          <span>
            <span className="font-semibold text-emerald-600 dark:text-emerald-400">
              {onlineCount}
            </span>{" "}
            online
          </span>
          <span>
            <span className="font-semibold text-sky-600 dark:text-sky-400">
              {wirelessCount}
            </span>{" "}
            wireless
          </span>
          <span>
            <span className="font-semibold text-foreground">
              {clients.length - onlineCount}
            </span>{" "}
            offline
          </span>
        </div>
      </div>

      {widgetLoading ? (
        <Skeleton className="h-96 w-full rounded-xl" />
      ) : (
        <div className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1fr)_360px]">
          <ClientTable
            clients={visible}
            selectedId={selectedId}
            sortKey={sortKey}
            onSort={setSortKey}
            onSelect={setSelectedId}
          />

          <div className="xl:sticky xl:top-6">
            {selectedClient ? (
              <ClientDetails
                client={selectedClient}
                canEdit={canEdit}
                onSaveLabel={saveLabel}
                onClearLabel={removeLabel}
              />
            ) : (
              <div className="flex flex-col items-center justify-center gap-3 rounded-xl border py-10 text-center">
                <span className="flex size-10 items-center justify-center rounded-full border bg-muted">
                  <MonitorSmartphone className="size-5 text-muted-foreground" aria-hidden />
                </span>
                <div className="space-y-1 px-4">
                  <p className="text-sm font-medium">No client selected</p>
                  <p className="text-sm text-muted-foreground">
                    Select a device from the list to see its full details.
                  </p>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {!widgetLoading && clients.length === 0 ? (
        <div className="rounded-xl border py-10">
          <EmptyState message="No clients discovered yet." />
        </div>
      ) : null}
    </div>
  );
}
