export type Source = "ssh" | "local" | "simulated" | "none";

export type CpuInfo = {
  load_1: number;
  load_5: number;
  load_15: number;
  cores: number;
  uptime_seconds: number;
  usage_percent: number | null;
  frequency_mhz: number | null;
};

export type MemoryInfo = {
  total_kb: number;
  free_kb: number;
  used_kb: number;
  buffered_kb: number;
  cached_kb: number | null;
  available_kb: number | null;
};

export type TemperatureReading = {
  zone: string;
  temperature_c: number;
};

export type StorageMount = {
  device: string;
  mountpoint: string;
  filesystem: string;
  total_bytes: number | null;
  used_bytes: number | null;
  available_bytes: number | null;
  use_percent: number | null;
};

export type NetworkAddress = {
  address: string;
  prefix: number;
  family: "ipv4" | "ipv6";
};

export type NetworkInterface = {
  name: string;
  up: boolean;
  proto: string | null;
  device: string | null;
  mac: string | null;
  link: boolean | null;
  speed_mbps: number | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
  addresses: NetworkAddress[];
};

export type FirewallZone = {
  name: string;
  input: string | null;
  output: string | null;
  forward: string | null;
  masquerade: boolean;
};

export type FirewallInfo = {
  zones: FirewallZone[];
  rules: unknown[];
};

export type WifiRadio = {
  name: string;
  up: boolean;
  mode: string | null;
  band: string | null;
  channel: number | null;
  frequency_mhz: number | null;
  tx_power: number | null;
  ssid: string | null;
  hwmode: string | null;
  station_count: number;
};

export type WifiClient = {
  mac: string;
  ssid: string | null;
  signal_dbm: number | null;
  tx_bytes: number | null;
  rx_bytes: number | null;
  connected_minutes: number | null;
};

export type WifiInfo = {
  radios: WifiRadio[];
  clients: WifiClient[];
};

export type ArpEntry = {
  ip: string;
  mac: string;
  interface: string;
  state: string;
};

export type RouteEntry = {
  destination: string;
  gateway: string | null;
  interface: string | null;
  metric: number | null;
  family: "ipv4" | "ipv6";
  flags: string;
};

export type VpnTunnel = {
  name: string;
  kind: "wireguard" | "openvpn" | "other";
  up: boolean;
  public_key: string | null;
  listen_port: number | null;
  endpoint: string | null;
  allowed_ips: string[];
  addresses: string[];
  peer_count: number;
  detail: Record<string, unknown>;
};

export type DhcpLease = {
  hostname: string;
  ip: string;
  mac: string | null;
  expires: string | null;
  interface: string | null;
};

export type KernelInfo = {
  kernel: string;
  release: string;
  hostname: string;
  model: string;
  architecture: string;
  board: string;
  system: string;
  version: string;
};

export type SnapshotMeta = {
  collected_at: string;
  device_id: string;
  transport: string;
  host: string;
  board: string;
  model: string;
  firmware: string;
  collectors_run: string[];
};

export type CollectError = {
  collector: string;
  error: string;
};

export type DeviceSnapshot = {
  meta: SnapshotMeta;
  cpu: CpuInfo | null;
  memory: MemoryInfo | null;
  temperature: TemperatureReading[];
  storage: StorageMount[];
  network: NetworkInterface[];
  firewall: FirewallInfo;
  wifi: WifiInfo;
  clients: DhcpLease[];
  arp: ArpEntry[];
  routing: RouteEntry[];
  vpn: VpnTunnel[];
  dhcp: unknown;
  packages: unknown[];
  kernel: KernelInfo;
  logs: unknown;
  errors: CollectError[];
};

export type DashboardUpdate = {
  type: "update";
  sequence: number;
  sent_at: string;
  source: Source;
  device_id: string;
  connected: boolean;
  error: string | null;
  snapshot: DeviceSnapshot | null;
};
