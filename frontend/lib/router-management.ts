import { API_BASE_URL } from "@/lib/api";

export type PackageManager = "apk" | "opkg" | "unknown";

export type ManagementPackage = {
  name: string;
  version: string;
  upgrade: string | null;
};

export type PackageInventory = {
  manager: PackageManager;
  count: number;
  upgrades_available: number;
  generated_at: string;
  packages: ManagementPackage[];
};

export type ManagementLogEntry = {
  raw: string;
  timestamp: string | null;
  facility: string | null;
  priority: string | null;
  ident: string | null;
  message: string;
};

export type LogResponse = {
  logs: ManagementLogEntry[];
  generated_at: string;
};

export type JobKind = "action" | "backup" | "bundle" | "restore" | "firewall";
export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export type ManagementJob = {
  id: string;
  kind: JobKind;
  status: JobStatus;
  message: string;
  error: string | null;
  result: Record<string, unknown> | null;
  pending_confirmation: boolean;
  created_at: string;
  artifact?: { name: string; media_type: string; size: number };
};

export type JobRequest = {
  kind: JobKind;
  action?: string;
  confirmed?: boolean;
  filename?: string;
  content_b64?: string;
  section?: string;
  enabled?: boolean;
};

async function request<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, { ...init, signal });
  const body = (await response.json().catch(() => null)) as
    | { detail?: string }
    | T
    | null;
  if (!response.ok) {
    const detail =
      (body && typeof body === "object" && "detail" in body
        ? (body as { detail?: string }).detail
        : null) ??
      `Request failed with status ${response.status}`;
    throw new Error(detail);
  }
  return body as T;
}

export function fetchPackages(refresh = false, signal?: AbortSignal): Promise<PackageInventory> {
  const query = refresh ? "?refresh=true" : "";
  return request<PackageInventory>(`/router/management/packages${query}`, undefined, signal);
}

export function refreshPackages(signal?: AbortSignal): Promise<PackageInventory> {
  return request<PackageInventory>("/router/management/packages/refresh", { method: "POST" }, signal);
}

export function fetchManagementLogs(lines = 500, signal?: AbortSignal): Promise<LogResponse> {
  return request<LogResponse>(`/router/management/logs?lines=${lines}`, undefined, signal);
}

export function startJob(payload: JobRequest, signal?: AbortSignal): Promise<ManagementJob> {
  return request<ManagementJob>(
    "/router/management/jobs",
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    signal,
  );
}

export function fetchJob(jobId: string, signal?: AbortSignal): Promise<ManagementJob> {
  return request<ManagementJob>(`/router/management/jobs/${jobId}`, undefined, signal);
}

export function confirmJob(jobId: string, signal?: AbortSignal): Promise<ManagementJob> {
  return request<ManagementJob>(
    `/router/management/jobs/${jobId}/confirm`,
    { method: "POST" },
    signal,
  );
}

export function toggleFirewallRule(
  section: string,
  enabled: boolean,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "firewall", section, enabled, confirmed: true }, signal);
}

export function jobArtifactUrl(jobId: string): string {
  return `${API_BASE_URL}/router/management/jobs/${jobId}/artifact`;
}

export async function downloadJobArtifact(jobId: string, filename?: string): Promise<void> {
  const response = await fetch(jobArtifactUrl(jobId));
  if (!response.ok) {
    throw new Error(`Download failed with status ${response.status}`);
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename ?? "download.bin";
  anchor.click();
  URL.revokeObjectURL(url);
}

export function readFileAsBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error("Could not read the selected file."));
    reader.onload = () => {
      const result = reader.result as string;
      resolve(result.slice(result.indexOf(",") + 1));
    };
    reader.readAsDataURL(file);
  });
}