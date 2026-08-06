"use client";

import { useEffect, useMemo, useRef } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { buildClients, type NetworkClient } from "@/lib/clients";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source } from "@/lib/dashboard";

/** How long a departed client stays listed as offline after its last sighting. */
const RETENTION_MS = 12 * 60 * 60 * 1000;

export type ClientsDataResult = {
  clients: NetworkClient[];
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
};

/**
 * Live client inventory, derived from the dashboard snapshot.
 *
 * Builds the unified client list on every poll and tracks each device's most
 * recent "seen online" timestamp so a client that drops out of the current
 * snapshot still reports when it was last present.
 */
export function useClients(): ClientsDataResult {
  const { update, status, loading, error, refetch } = useDashboardData();

  const snapshot = update?.snapshot ?? null;
  const updatedAt = update?.sent_at ?? null;

  const clients = useMemo(
    () => buildClients(snapshot, updatedAt),
    [snapshot, updatedAt],
  );

  const lastSeenRef = useRef<Record<string, string>>({});
  const previousRef = useRef<Map<string, NetworkClient>>(new Map());

  useEffect(() => {
    if (!update?.connected || snapshot === null) {
      return;
    }
    const stamp = update.sent_at;
    for (const client of clients) {
      if (client.online && stamp) {
        lastSeenRef.current[client.id] = stamp;
      }
    }
  }, [clients, snapshot, update]);

  const result = useMemo(() => {
    const prev = previousRef.current;
    const previous = new Map<string, NetworkClient>();
    const enriched: NetworkClient[] = clients.map((client) => {
      const lastSeen: string | null = client.online
        ? lastSeenRef.current[client.id] ?? updatedAt
        : lastSeenRef.current[client.id] ?? null;
      const enrichedClient = { ...client, last_seen: lastSeen };
      previous.set(client.id, enrichedClient);
      return enrichedClient;
    });
    // Carry forward devices that were seen online but are no longer in the
    // current snapshot, so recently departed clients stay listed as offline
    // with their last known details. Offline entries older than the retention
    // window are dropped so the inventory does not grow unbounded.
    const cutoff = updatedAt ? Date.parse(updatedAt) - RETENTION_MS : Number.NaN;
    for (const [id, prior] of prev) {
      if (previous.has(id)) {
        continue;
      }
      if (prior.last_seen && Date.parse(prior.last_seen) >= cutoff) {
        const carried = { ...prior, online: false };
        previous.set(id, carried);
        enriched.push(carried);
      }
    }
    previousRef.current = previous;
    return enriched;
  }, [clients, updatedAt]);

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  return {
    clients: result,
    status,
    loading,
    error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    refetch,
  };
}