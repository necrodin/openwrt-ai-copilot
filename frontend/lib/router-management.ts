import { API_BASE_URL } from "@/lib/api";
import { authHeaders } from "@/lib/auth";

export type PackageManager = "apk" | "opkg" | "unknown";

export type ManagementPackage = {
  name: string;
  version: string;
  upgrade: string | null;
  size: number | null;
  architecture: string | null;
  description: string | null;
  depends: string[];
  source?: string | null;
  license?: string | null;
};

export type PackageInventory = {
  manager: PackageManager;
  count: number;
  upgrades_available: number;
  generated_at: string;
  packages: ManagementPackage[];
};

export type PackageFeed = {
  type: string;
  name: string;
  url: string;
  source: string;
};

export type PackageFeeds = {
  manager: PackageManager;
  count: number;
  last_update: number | null;
  feeds: PackageFeed[];
};

export type PackageSearchResult = {
  name: string;
  version: string;
  description: string;
};

export type PackageSearchResponse = {
  query: string;
  manager: PackageManager;
  count: number;
  results: PackageSearchResult[];
  repository?: {
    status: "ok" | "manager-unavailable" | "repository-unavailable" | "index-unavailable";
    available: boolean;
    reason?: string | null;
    detail?: string[];
  } | null;
};

export type PackageDetails = {
  name: string;
  version: string;
  architecture: string | null;
  description: string;
  homepage: string;
  maintainer: string;
  license: string;
  depends: string[];
  section: string | null;
  installed_size: number | null;
  download_size: number | null;
};

export type PackageAction = "install" | "remove" | "upgrade" | "reinstall";

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

export type JobKind = "action" | "backup" | "bundle" | "restore" | "firewall" | "wireless" | "vpn" | "dhcp" | "dns" | "network" | "system" | "packages" | "storage" | "services";
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

export type DhcpHostPayload = {
  section?: string;
  hostname?: string;
  ip?: string;
  mac?: string;
};

export type JobRequest = {
  kind: JobKind;
  action?: string;
  confirmed?: boolean;
  filename?: string;
  content_b64?: string;
  section?: string;
  enabled?: boolean;
  hostname?: string;
  ip?: string;
  mac?: string;
  server?: string;
  timezone?: string;
  language?: string;
  notes?: string;
  name?: string;
  target?: string;
};

async function request<T>(path: string, init?: RequestInit, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: authHeaders(init?.headers),
    signal,
  });
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

export function fetchPackageFeeds(signal?: AbortSignal): Promise<PackageFeeds> {
  return request<PackageFeeds>("/router/management/packages/feeds", undefined, signal);
}

export function searchRepository(query: string, signal?: AbortSignal): Promise<PackageSearchResponse> {
  return request<PackageSearchResponse>(
    `/router/management/packages/search?q=${encodeURIComponent(query)}`,
    undefined,
    signal,
  );
}

export function fetchPackageDetails(name: string, signal?: AbortSignal): Promise<PackageDetails> {
  return request<PackageDetails>(
    `/router/management/packages/${encodeURIComponent(name)}`,
    undefined,
    signal,
  );
}

export function runPackageAction(
  action: PackageAction,
  name: string,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "packages", action, name, confirmed: true }, signal);
}

export function updatePackageFeeds(signal?: AbortSignal): Promise<ManagementJob> {
  return startJob({ kind: "packages", action: "update-feeds", confirmed: true }, signal);
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

export function toggleWirelessSsid(
  section: string,
  enabled: boolean,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "wireless", section, enabled, confirmed: true }, signal);
}

export function toggleVpnInstance(
  section: string,
  enabled: boolean,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "vpn", section, enabled, confirmed: true }, signal);
}

export function setDhcpEnabled(
  enabled: boolean,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "dhcp", action: "set-enabled", enabled, confirmed: true }, signal);
}

export type DhcpHostAction = "host-add" | "host-edit" | "host-delete" | "host-toggle";

export function runDhcpHost(
  action: DhcpHostAction,
  payload: DhcpHostPayload,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob(
    { kind: "dhcp", action, confirmed: true, ...payload },
    signal,
  );
}

export type DnsHost = {
  ip: string;
  hostname: string;
};

export type DnsInfo = {
  ok: boolean;
  service: {
    name: string;
    running: boolean;
    enabled: boolean;
    configured: boolean;
  };
  upstream: string[];
  servers: string[];
  domain: string | null;
  hosts: DnsHost[];
  counts: {
    servers: number;
    hosts: number;
  };
  error?: string | null;
};

export type DnsAction =
  | "reload"
  | "restart"
  | "set-enabled"
  | "add-server"
  | "remove-server"
  | "add-host"
  | "remove-host";

export function fetchDnsInfo(signal?: AbortSignal): Promise<DnsInfo> {
  return request<DnsInfo>("/router/management/dns", undefined, signal);
}

export function runDnsJob(
  action: DnsAction,
  payload: {
    server?: string;
    hostname?: string;
    ip?: string;
    enabled?: boolean;
  } = {},
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "dns", action, confirmed: true, ...payload }, signal);
}

export type NetworkAction =
  | "interface-restart"
  | "interface-renew"
  | "interface-release"
  | "interface-enable"
  | "interface-disable";

export function runNetworkJob(
  action: NetworkAction,
  section: string,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "network", action, section, confirmed: true }, signal);
}

export function jobArtifactUrl(jobId: string): string {
  return `${API_BASE_URL}/router/management/jobs/${jobId}/artifact`;
}

export type RouterProcess = {
  pid: number;
  cpu: number;
  mem: number | null;
  rss: number;
  vsz: number | null;
  user: string;
  name: string;
  command: string;
};

export type ProcessResponse = {
  count: number;
  generated_at: string;
  processes: RouterProcess[];
};

export function fetchProcesses(signal?: AbortSignal): Promise<ProcessResponse> {
  return request<ProcessResponse>("/router/management/processes", undefined, signal);
}

export type SystemNtp = {
  enabled: boolean;
  servers: string[];
  offset: number | null;
};

export type SystemInfo = {
  hostname: string;
  model: string;
  board: string;
  vendor: string;
  architecture: string;
  target: string;
  firmware: string;
  release: string;
  revision: string;
  build_date: string;
  kernel: string;
  machine: string;
  device_tree: string;
  endianness: "little" | "big" | null;
  flash_bytes: number | null;
  root_filesystem: string | null;
  overlay_filesystem: string | null;
  timezone: string;
  zonename: string;
  language: string;
  notes: string;
  local_time: string;
  epoch: number | null;
  uptime_seconds: number | null;
  boot_time: number | null;
  ntp: SystemNtp;
  generated_at: string;
};

export type SystemConfig = {
  hostname?: string;
  timezone?: string;
  language?: string;
  notes?: string;
};

export function fetchSystemInfo(signal?: AbortSignal): Promise<SystemInfo> {
  return request<SystemInfo>("/router/management/system", undefined, signal);
}

export function saveSystemConfig(config: SystemConfig, signal?: AbortSignal): Promise<ManagementJob> {
  return startJob(
    { kind: "system", action: "save-config", confirmed: true, ...config },
    signal,
  );
}

export function killProcess(pid: number, signal?: AbortSignal): Promise<{ ok: boolean; message: string }> {
  return request<{ ok: boolean; message: string }>(
    `/router/management/processes/${pid}/kill`,
    { method: "POST" },
    signal,
  );
}

export async function downloadJobArtifact(jobId: string, filename?: string): Promise<void> {
  const response = await fetch(jobArtifactUrl(jobId), {
    headers: authHeaders(),
  });
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

export type StorageDevice = {
  name: string;
  type: string;
  vendor: string;
  model: string;
  size: number;
  status: string;
};

export type StorageMountRow = {
  device: string;
  mountpoint: string;
  filesystem: string;
  options: string;
  total_bytes: number;
  used_bytes: number;
  available_bytes: number;
  use_percent: number | null;
  overlay: boolean;
  rootfs: boolean;
};

export type StorageUsbDevice = {
  device: string;
  vendor: string;
  model: string;
  capacity: number;
  mounted: boolean;
  mountpoint: string | null;
};

export type StorageInfo = {
  generated_at: string;
  devices: StorageDevice[];
  mounts: StorageMountRow[];
  usb: StorageUsbDevice[];
  rootfs: StorageMountRow | null;
  overlayfs: StorageMountRow | null;
  total_bytes: number | null;
  used_bytes: number | null;
  available_bytes: number | null;
  use_percent: number | null;
};

export type StorageAction = "mount" | "unmount" | "remount";

export function fetchStorageInfo(signal?: AbortSignal): Promise<StorageInfo> {
  return request<StorageInfo>("/router/management/storage", undefined, signal);
}

export function runStorageAction(
  action: StorageAction,
  target: string,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "storage", action, target, confirmed: true }, signal);
}

export type ServiceAction = "start" | "stop" | "restart" | "enable" | "disable";

export type RouterService = {
  name: string;
  description: string;
  running: boolean;
  enabled: boolean | null;
  pid: number | null;
  uptime: number | null;
  restart_count: number | null;
  instances: number;
};

export type ServicesInfo = {
  generated_at: string;
  count: number;
  running_count: number;
  enabled_count: number;
  ubus: boolean;
  services: RouterService[];
};

export function fetchServicesInfo(signal?: AbortSignal): Promise<ServicesInfo> {
  return request<ServicesInfo>("/router/management/services", undefined, signal);
}

export function runServiceAction(
  action: ServiceAction,
  name: string,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return request<ManagementJob>(
    `/router/management/services/${encodeURIComponent(name)}/${action}`,
    { method: "POST" },
    signal,
  );
}

export type FirewallZone = {
  name: string;
  section: string;
  enabled: boolean;
  family: string | null;
  input: string | null;
  output: string | null;
  forward: string | null;
  masquerade: boolean;
  mtu_fix: boolean;
  network: string | string[] | null;
};

export type FirewallInterface = {
  name: string;
  device: string | null;
  up: boolean;
  proto: string | null;
};

export type FirewallRule = {
  name: string;
  section: string;
  enabled: boolean;
  target: string | null;
  src: string | null;
  dest: string | null;
  proto: string | null;
  family: string | null;
  src_port: string | null;
  dest_port: string | null;
};

export type FirewallPortForward = {
  name: string;
  section: string;
  enabled: boolean;
  target: string | null;
  proto: string | null;
  src: string | null;
  src_dport: string | null;
  src_ip: string | null;
  dest: string | null;
  dest_ip: string | null;
  dest_port: string | null;
  family: string | null;
};

export type FirewallForward = {
  name: string;
  section: string;
  enabled: boolean;
  src: string | null;
  dest: string | null;
  family: string | null;
};

export type FirewallNat = {
  name: string;
  section: string;
  enabled: boolean;
  target: string | null;
  proto: string | null;
  family: string | null;
  src: string | null;
  dest: string | null;
  src_dport: string | null;
  dest_ip: string | null;
  dest_port: string | null;
};

export type FirewallIpSet = {
  name: string;
  section: string;
  enabled: boolean;
  family: string | null;
  match: string | null;
  entries: string[];
  count: number;
};

export type FirewallInclude = {
  name: string;
  section: string;
  path: string | null;
  enabled: boolean;
};

export type FirewallDefaults = {
  input: string | null;
  output: string | null;
  forward: string | null;
  masquerade: boolean;
  syn_flood: boolean;
  osf: boolean;
  mtu: number | null;
};

export type FirewallInfo = {
  generated_at: string;
  enabled: boolean;
  running: boolean;
  version: string | null;
  defaults: FirewallDefaults | null;
  zones: FirewallZone[];
  rules: FirewallRule[];
  port_forwards: FirewallPortForward[];
  forwardings: FirewallForward[];
  nat: FirewallNat[];
  includes: FirewallInclude[];
  ipsets: FirewallIpSet[];
  ipsets_available: boolean;
  interfaces: FirewallInterface[];
  conntrack: { max: number | null; count: number | null } | null;
  counts: {
    zones: number;
    rules: number;
    port_forwards: number;
    forwardings: number;
    nat: number;
    includes: number;
    ipsets: number;
  };
};

export type FirewallAction =
  | "restart"
  | "reload"
  | "enable"
  | "disable"
  | "enable-rule"
  | "disable-rule"
  | "enable-zone"
  | "disable-zone"
  | "enable-forwarding"
  | "disable-forwarding";

export function fetchFirewallInfo(signal?: AbortSignal): Promise<FirewallInfo> {
  return request<FirewallInfo>("/router/management/firewall", undefined, signal);
}

export function runFirewallAction(
  action: FirewallAction,
  section?: string,
  signal?: AbortSignal,
): Promise<ManagementJob> {
  return startJob({ kind: "firewall", action, section, confirmed: true }, signal);
}