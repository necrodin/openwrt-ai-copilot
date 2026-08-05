/**
 * Centralized version module.
 *
 * Exposes the application version, frontend version, backend version (fetched
 * from the live health endpoint), git commit, build date, and environment —
 * the single source of truth shown on the About page and in the footer.
 */

import { API_BASE_URL, fetchHealth, type HealthResponse } from "@/lib/api";
import { SITE_CONFIG } from "@/lib/site-config";

export type FrontendVersionInfo = {
  appName: string;
  /** Application version (shared, from config). */
  version: string;
  /** Frontend build version. */
  frontendVersion: string;
  /** Short git commit hash when the build was stamped with one. */
  gitCommit: string | null;
  /** Build date ISO string when the build was stamped with one. */
  buildDate: string | null;
  environment: string;
};

export type BackendVersionInfo = {
  service: string;
  version: string;
  environment: string;
  status: string;
};

/** Synchronous, build-time stamped version information. */
export function getFrontendVersionInfo(): FrontendVersionInfo {
  const gitCommit = SITE_CONFIG.gitCommit
    ? SITE_CONFIG.gitCommit.slice(0, 8)
    : null;
  return {
    appName: SITE_CONFIG.name,
    version: SITE_CONFIG.version,
    frontendVersion: SITE_CONFIG.frontendVersion,
    gitCommit,
    buildDate: SITE_CONFIG.buildDate,
    environment: SITE_CONFIG.environment,
  };
}

/** Fetch the live backend version from the health endpoint. */
export async function fetchBackendVersion(
  signal?: AbortSignal,
): Promise<BackendVersionInfo> {
  try {
    const health: HealthResponse = await fetchHealth(signal);
    return {
      service: health.service,
      version: health.version,
      environment: health.environment,
      status: health.status,
    };
  } catch {
    return {
      service: "OpenWrt AI Copilot",
      version: "unavailable",
      environment: SITE_CONFIG.environment,
      status: "unknown",
    };
  }
}

export { API_BASE_URL };
