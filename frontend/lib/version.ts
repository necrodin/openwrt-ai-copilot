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
  /** Application version (shared, from config). `null` when not stamped. */
  version: string | null;
  /** Frontend build version. `null` when not stamped. */
  frontendVersion: string | null;
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
  /** Git commit reported by the live backend, when the deployment is stamped. */
  gitCommit: string | null;
  /** Build date reported by the live backend, when the deployment is stamped. */
  buildDate: string | null;
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
      gitCommit: health.git_commit ?? null,
      buildDate: health.build_date ?? null,
    };
  } catch {
    return {
      service: "OpenWrt AI Copilot",
      version: "unavailable",
      environment: SITE_CONFIG.environment,
      status: "unknown",
      gitCommit: null,
      buildDate: null,
    };
  }
}

export { API_BASE_URL };
