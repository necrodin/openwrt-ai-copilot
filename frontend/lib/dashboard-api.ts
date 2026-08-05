import { API_BASE_URL } from "@/lib/api";
import type { DashboardUpdate } from "@/lib/dashboard";

export type RouterSystem = {
  hostname?: string | null;
  model?: string | null;
  board?: string | null;
  firmware?: string | null;
  kernel?: string | null;
  architecture?: string | null;
  uptime?: string | null;
};

export type RouterCpu = {
  usage_percent?: number | null;
  cores?: number | null;
  load_1?: number | null;
  load_5?: number | null;
  load_15?: number | null;
};

export type RouterMemory = {
  total_kb?: number | null;
  used_kb?: number | null;
  used_percent?: number | null;
};

export type RouterStorage = {
  mountpoint?: string | null;
  device?: string | null;
  filesystem?: string | null;
  total_gb?: number | null;
  used_gb?: number | null;
  use_percent?: number | null;
};

export type RouterSnapshotData = {
  system: RouterSystem | null;
  cpu: RouterCpu | null;
  memory: RouterMemory | null;
  storage: RouterStorage[] | null;
};

export type RouterFinding = {
  severity: string;
  category: string;
  title: string;
  description: string;
  recommendation: string;
};

export type RouterRecommendation = {
  id: string;
  priority: string;
  category: string;
  title: string;
  description: string;
  action: string;
  impact: string;
};

export type RouterStatusResponse = {
  connected: boolean;
  source: string;
  device_id: string;
  last_snapshot_at: string | null;
  sequence: number;
  error: string | null;
  server_time: string;
  snapshot: RouterSnapshotData | null;
  diagnosis: RouterFinding[];
  recommendations: RouterRecommendation[];
};

/**
 * Returns the most recent dashboard update. This is the REST fallback for the
 * live WebSocket feed and is polled by `useDashboardData`.
 */
export async function fetchDashboardLatest(
  signal?: AbortSignal,
): Promise<DashboardUpdate> {
  const res = await fetch(`${API_BASE_URL}/dashboard/latest`, { signal });
  if (!res.ok) {
    throw new Error(`Dashboard request failed with status ${res.status}`);
  }
  return (await res.json()) as DashboardUpdate;
}

/**
 * Returns connection state plus the derived router snapshot, diagnosis, and
 * recommendations from `/router/status`.
 */
export async function fetchRouterStatus(
  signal?: AbortSignal,
): Promise<RouterStatusResponse> {
  const res = await fetch(`${API_BASE_URL}/router/status`, { signal });
  if (!res.ok) {
    throw new Error(`Router status request failed with status ${res.status}`);
  }
  return (await res.json()) as RouterStatusResponse;
}
