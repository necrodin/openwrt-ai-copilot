"use client";

import { useEffect, useState } from "react";

import { fetchHealth, type HealthResponse } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";

export function HealthStatus() {
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch(() => setError(true));
    return () => controller.abort();
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
