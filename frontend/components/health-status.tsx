"use client";

import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

const POLL_INTERVAL_MS = 10_000;

export function HealthStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    const tick = async () => {
      if (!active) {
        return;
      }
      try {
        const next = await fetchHealth(controller.signal);
        if (active) {
          setHealth(next);
          setError(false);
        }
      } catch (err) {
        if (active && !(err instanceof DOMException && err.name === "AbortError")) {
          setError(true);
        }
      }
    };

    void tick();
    const interval = window.setInterval(tick, POLL_INTERVAL_MS);
    return () => {
      active = false;
      controller.abort();
      window.clearInterval(interval);
    };
  }, []);

  if (error) {
    return <Badge variant="destructive">API unreachable</Badge>;
  }

  if (!health) {
    return <Skeleton className="h-5 w-28" />;
  }

  return (
    <Badge variant={health.status === "ok" ? "default" : "destructive"}>
      {health.service} {health.version} · {health.status}
    </Badge>
  );
}
