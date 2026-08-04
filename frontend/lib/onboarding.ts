import { API_BASE_URL } from "@/lib/api";

export type AuthType = "password" | "key";

export type RouterCredentials = {
  host: string;
  port: number;
  username: string;
  authType: AuthType;
  password: string;
  privateKey: string;
};

export type ConnectionTestResult = {
  ok: boolean;
  error: string | null;
};

export type NetworkInterfaceAddress = {
  address: string;
  prefix: number;
  family: "ipv4" | "ipv6";
};

export type NetworkInterfaceSummary = {
  name: string;
  up: boolean;
  proto: string | null;
  mac: string | null;
  link: boolean | null;
  addresses: NetworkInterfaceAddress[];
};

export type WifiRadioSummary = {
  name: string;
  up: boolean;
  mode: string | null;
  band: string | null;
  channel: number | null;
  frequency_mhz: number | null;
  tx_power: number | null;
  ssid: string | null;
  station_count: number;
};

export type DeviceInfo = {
  ok: boolean;
  is_openwrt: boolean;
  host: string;
  model: string | null;
  firmware: string | null;
  hostname: string | null;
  device_id: string | null;
  kernel?: string | null;
  architecture?: string | null;
  cpu?: {
    cores: number | null;
    usage_percent: number | null;
    load_1: number | null;
  } | null;
  memory?: {
    total_kb: number | null;
    used_kb: number | null;
    used_percent: number | null;
  } | null;
  network_interfaces?: NetworkInterfaceSummary[] | null;
  wifi_radios?: WifiRadioSummary[] | null;
  packages_count?: number | null;
  error?: string | null;
};

export type SavedRouter = {
  id: number;
  name: string;
  host: string;
  port: number;
  username: string;
  auth_type: AuthType;
  device_id: string | null;
  created_at: string | null;
};

export type ConnectionsResponse = {
  routers: SavedRouter[];
};

export type SaveResult = SavedRouter & { message: string };

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`Request failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    throw new Error(`Request failed with status ${res.status}`);
  }
  return (await res.json()) as T;
}

export function toRequestPayload(credentials: RouterCredentials) {
  return {
    host: credentials.host,
    port: credentials.port,
    username: credentials.username,
    auth_type: credentials.authType,
    password: credentials.authType === "password" ? credentials.password : null,
    private_key: credentials.authType === "key" ? credentials.privateKey : null,
  };
}

export function testConnection(
  credentials: RouterCredentials,
): Promise<ConnectionTestResult> {
  return postJson("/router/test-connection", toRequestPayload(credentials));
}

export function detectDevice(credentials: RouterCredentials): Promise<DeviceInfo> {
  return postJson("/router/detect", toRequestPayload(credentials));
}

export function saveRouter(
  name: string,
  credentials: RouterCredentials,
): Promise<SaveResult> {
  return postJson("/router/save", {
    ...toRequestPayload(credentials),
    name,
  });
}

export function listConnections(): Promise<ConnectionsResponse> {
  return getJson("/router/connections");
}
