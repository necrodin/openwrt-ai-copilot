import { authHeaders } from "@/lib/auth";

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api/v1";

export type HealthResponse = {
  status: string;
  service: string;
  version: string;
  environment: string;
  git_commit?: string | null;
  build_date?: string | null;
};

export async function fetchHealth(
  signal?: AbortSignal,
): Promise<HealthResponse> {
  const res = await fetch(`${API_BASE_URL}/health`, {
    headers: authHeaders(),
    signal,
  });
  if (!res.ok) {
    throw new Error(`Health check failed with status ${res.status}`);
  }
  return (await res.json()) as HealthResponse;
}
