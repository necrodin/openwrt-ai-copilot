/**
 * Internet speed-test API client and presentation helpers.
 *
 * Mirrors the backend surface under /api/v1/network/speed-test. The test is a
 * read-only measurement (any authenticated role may run it); it never executes
 * router commands. The result intentionally keeps a flat, minimal shape so a
 * future Copilot feature can read the latest result without redesigning the
 * API — see `latestSpeedTest()`.
 */

import { API_BASE_URL } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type SpeedTestResult = {
  download_mbps: number | null;
  upload_mbps: number | null;
  ping_ms: number | null;
  jitter_ms: number | null;
  timestamp: string;
  duration_ms: number;
  /** Human-readable notes when a sub-measurement could not be measured. */
  limitations: string[];
  complete: boolean;
};

export type LatestSpeedTestResponse = {
  result: SpeedTestResult | null;
};

/** Coarse stage shown while a test is running (the backend runs as one call). */
export type SpeedTestStage = "testing" | "latency" | "downloading" | "uploading";

/** Run an internet speed test (read-only measurement; one at a time). */
export async function runSpeedTest(): Promise<SpeedTestResult> {
  const res = await fetch(`${API_BASE_URL}/network/speed-test`, {
    method: "POST",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(await speedTestErrorMessage(res));
  }
  return (await res.json()) as SpeedTestResult;
}

/** Fetch the most recent speed-test result (``result: null`` before the first
 * run). Lets the dashboard and future Copilot features read it without running
 * a new test. */
export async function latestSpeedTest(): Promise<LatestSpeedTestResponse> {
  const res = await fetch(`${API_BASE_URL}/network/speed-test`, {
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(await speedTestErrorMessage(res));
  }
  return (await res.json()) as LatestSpeedTestResponse;
}

async function speedTestErrorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return data.detail;
    }
  } catch {
    // Non-JSON body — fall through to the status-based message.
  }
  return `Speed test failed with status ${res.status}`;
}

/** Human-readable progress label for the stage currently shown. */
export function speedStageLabel(stage: SpeedTestStage): string {
  switch (stage) {
    case "latency":
      return "Latency…";
    case "downloading":
      return "Download…";
    case "uploading":
      return "Upload…";
    case "testing":
      return "Testing…";
  }
}

/** Format a Mbps figure; ``null`` (not measured) renders as an em dash. */
export function formatSpeed(mbps: number | null): string {
  return mbps === null ? "—" : mbps.toFixed(1);
}

/** Format a latency figure in ms; ``null`` (not measured) renders as an em dash. */
export function formatLatency(ms: number | null): string {
  return ms === null ? "—" : ms.toFixed(1);
}

/** "Last test" label: a formatted timestamp or "Never" when none exists. */
export function formatSpeedTestTimestamp(iso: string | null | undefined): string {
  if (!iso) {
    return "Never";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "Never";
  }
  return date.toLocaleString([], {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
