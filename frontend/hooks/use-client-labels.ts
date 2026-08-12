"use client";

import { useCallback, useEffect, useState } from "react";

import {
  deleteClientLabel,
  listClientLabels,
  saveClientLabel,
} from "@/lib/client-labels";
import { canonicalizeMac, type ClientLabel } from "@/lib/clients";

export type ClientLabelsResult = {
  labels: ClientLabel[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  save: (mac: string, label: string) => Promise<void>;
  remove: (mac: string) => Promise<void>;
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Operator-assigned client labels (per-MAC metadata stored in the backend).
 *
 * Loads the current labels once and keeps the local list in sync with saves
 * and deletes, so the Clients page reflects edits without a full refetch.
 */
export function useClientLabels(): ClientLabelsResult {
  const [labels, setLabels] = useState<ClientLabel[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const data = await listClientLabels();
      setLabels(data.labels);
      setError(null);
    } catch (e) {
      setError(message(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const save = useCallback(async (mac: string, label: string) => {
    const record = await saveClientLabel(mac, label);
    const key = canonicalizeMac(record.mac_address);
    setLabels((previous) => {
      const rest = previous.filter(
        (entry) => canonicalizeMac(entry.mac_address) !== key,
      );
      return [...rest, record].sort((a, b) =>
        a.mac_address.localeCompare(b.mac_address),
      );
    });
    setError(null);
  }, []);

  const remove = useCallback(async (mac: string) => {
    await deleteClientLabel(mac);
    const key = canonicalizeMac(mac);
    setLabels((previous) =>
      previous.filter((entry) => canonicalizeMac(entry.mac_address) !== key),
    );
    setError(null);
  }, []);

  return { labels, loading, error, refresh, save, remove };
}
