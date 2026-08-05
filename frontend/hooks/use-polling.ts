"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type PollingResult<T> = {
  data: T | null;
  loading: boolean;
  error: string | null;
  refetch: () => void;
};

type Options = {
  /** Delay between polls in milliseconds. Defaults to 5000. */
  intervalMs?: number;
  /** When false the poller is idle and never fires requests. */
  enabled?: boolean;
};

/**
 * Generic polling hook.
 *
 * Runs a fetcher immediately, then re-runs it on a fixed interval. The current
 * request is aborted on unmount and on `refetch`. The fetcher is kept in a ref
 * so callers may pass inline callbacks without re-subscribing every render.
 *
 * This is intentionally transport-agnostic: swapping REST polling for a
 * WebSocket subscription later only changes *which* hook a component consumes,
 * never the component itself.
 */
export function usePolling<T>(
  fetcher: (signal: AbortSignal) => Promise<T>,
  { intervalMs = 5000, enabled = true }: Options = {},
): PollingResult<T> {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  const fetcherRef = useRef(fetcher);
  fetcherRef.current = fetcher;

  useEffect(() => {
    if (!enabled) {
      setLoading(false);
      setError(null);
      return;
    }

    let cancelled = false;
    let timeout: number | undefined;
    let controller: AbortController | undefined;

    const run = async () => {
      controller = new AbortController();
      const signal = controller.signal;
      try {
        const result = await fetcherRef.current(signal);
        if (!cancelled) {
          setData(result);
          setError(null);
        }
      } catch (err) {
        if (!cancelled && !signal.aborted) {
          setError(err instanceof Error ? err.message : "Request failed");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
          timeout = window.setTimeout(() => {
            void run();
          }, intervalMs);
        }
      }
    };

    void run();

    return () => {
      cancelled = true;
      if (timeout !== undefined) {
        window.clearTimeout(timeout);
      }
      controller?.abort();
    };
  }, [enabled, intervalMs, tick]);

  const refetch = useCallback(() => {
    setLoading(true);
    setTick((value) => value + 1);
  }, []);

  return { data, loading, error, refetch };
}
