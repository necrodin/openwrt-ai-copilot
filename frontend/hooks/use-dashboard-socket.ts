"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import type { DashboardUpdate } from "@/lib/dashboard";
import {
  dashboardSocketUrl,
  parseUpdate,
  type ConnectionStatus,
} from "@/lib/dashboard-utils";

/**
 * Subscribes to the live dashboard WebSocket. Automatically reconnects with
 * capped exponential backoff and exposes the latest update plus connection
 * status. The update is applied only when it contains a snapshot.
 */
export function useDashboardSocket() {
  const [update, setUpdate] = useState<DashboardUpdate | null>(null);
  const [status, setStatus] = useState<ConnectionStatus>("connecting");
  const attempts = useRef(0);
  const socket = useRef<WebSocket | null>(null);

  const close = useCallback(() => {
    socket.current?.close();
    socket.current = null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    let retry: number | undefined;
    let delay = 500;

    const connect = () => {
      if (cancelled) {
        return;
      }
      setStatus(attempts.current === 0 ? "connecting" : "reconnecting");
      const ws = new WebSocket(dashboardSocketUrl());
      socket.current = ws;

      ws.onopen = () => {
        attempts.current = 0;
        delay = 500;
        setStatus("live");
      };

      ws.onmessage = (event) => {
        const next = parseUpdate(event.data as string);
        if (next !== null) {
          setUpdate(next);
        }
      };

      ws.onclose = () => {
        if (cancelled) {
          return;
        }
        setStatus("reconnecting");
        retry = window.setTimeout(() => {
          attempts.current += 1;
          connect();
        }, delay);
        delay = Math.min(delay * 2, 10_000);
      };
    };

    connect();
    return () => {
      cancelled = true;
      if (retry !== undefined) {
        window.clearTimeout(retry);
      }
      close();
    };
  }, [close]);

  return { update, status };
}
