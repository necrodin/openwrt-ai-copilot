export type Source = "ssh" | "local" | "simulated" | "none";

export type CpuInfo = {
  load_1: number;
  load_5: number;
  load_15: number;
  cores: number;
  uptime_seconds: number;
  usage_percent: number | null;
  frequency_mhz: number | null;
  model: string | null;
  architecture: string | null;
  temperature_c: number | null;
};

export type MemoryInfo = {
  total_kb: number;
  free_kb: number;
  used_kb: number;
  buffered_kb: number;
  cached_kb: number | null;
  available_kb: number | null;
  swap_total_kb: number | null;
  swap_free_kb: number | null;
  swap_used_kb: number | null;
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
  inodes_total: number | null;
  inodes_used: number | null;
  inodes_available: number | null;
  inode_use_percent: number | null;
  wear: number | null;
  health: string | null;
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
  mtu: number | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
  is_bridge: boolean;
  vlan_id: number | null;
  gateway: string | null;
  addresses: NetworkAddress[];
};

export type NetworkStatus = {
  gateway: string | null;
  dns: string[];
  wan_interface: string | null;
};

export type FirewallZone = {
  name: string;
  input: string | null;
  output: string | null;
  forward: string | null;
  masquerade: boolean;
  network: string[];
  mtu_fix: boolean;
};

export type FirewallRule = {
  name: string;
  src: string | null;
  dest: string | null;
  proto: string | null;
  target: string | null;
  family: string | null;
  src_port: string | null;
  dest_port: string | null;
  enabled: boolean;
  section: string;
};

export type FirewallForward = {
  name: string;
  proto: string | null;
  src: string | null;
  src_dport: string | null;
  src_ip: string | null;
  dest: string | null;
  dest_ip: string | null;
  dest_port: string | null;
  target: string | null;
  enabled: boolean;
  section: string;
};

export type FirewallNat = {
  name: string;
  target: string | null;
  family: string | null;
  src: string | null;
  src_dport: string | null;
  dest: string | null;
  dest_ip: string | null;
  dest_port: string | null;
  proto: string | null;
  enabled: boolean;
  section: string;
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

export type FirewallStatus = {
  running: boolean;
  enabled: boolean;
  version: string | null;
};

export type FirewallConntrack = {
  count: number | null;
  max: number | null;
};

export type FirewallInfo = {
  defaults: FirewallDefaults | null;
  zones: FirewallZone[];
  rules: FirewallRule[];
  forwards: FirewallForward[];
  nat: FirewallNat[];
  status: FirewallStatus | null;
  conntrack: FirewallConntrack | null;
};

export const EMPTY_FIREWALL: FirewallInfo = {
  defaults: null,
  zones: [],
  rules: [],
  forwards: [],
  nat: [],
  status: null,
  conntrack: null,
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
  width_mhz: number | null;
  station_count: number;
  country: string | null;
  hardware: string | null;
};

export type WifiNetwork = {
  ssid: string;
  radio: string;
  interface: string | null;
  mode: string | null;
  encryption: string | null;
  hidden: boolean;
  enabled: boolean;
  network: string | null;
  client_count: number;
  section: string;
};

export type WifiClient = {
  mac: string;
  ssid: string | null;
  signal_dbm: number | null;
  tx_bytes: number | null;
  rx_bytes: number | null;
  connected_minutes: number | null;
  noise: number | null;
  rx_rate: number | null;
  tx_rate: number | null;
  interface: string | null;
  connected_time: number | null;
};

export type WifiInfo = {
  radios: WifiRadio[];
  networks: WifiNetwork[];
  clients: WifiClient[];
};

export const EMPTY_WIFI: WifiInfo = {
  radios: [],
  networks: [],
  clients: [],
};

export type ArpEntry = {
  ip: string;
  mac: string;
  interface: string;
  state: string;
};

export type NeighborEntry = {
  ip: string;
  mac: string | null;
  interface: string | null;
  state: string | null;
  family: "ipv6" | "ipv4";
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
  kind: "wireguard" | "openvpn" | "ipsec" | "tailscale" | "zerotier" | "other";
  up: boolean;
  enabled: boolean;
  public_key: string | null;
  listen_port: number | null;
  endpoint: string | null;
  allowed_ips: string[];
  addresses: string[];
  peer_count: number;
  rx_bytes: number | null;
  tx_bytes: number | null;
  version: string | null;
  uptime_seconds: number | null;
  detail: Record<string, unknown>;
};

export type DhcpLease = {
  hostname: string;
  ip: string;
  mac: string | null;
  expires: string | null;
  interface: string | null;
};

export type DhcpPool = {
  name: string;
  interface: string | null;
  start: string | null;
  limit: number | null;
  leasetime: string | null;
  range_end: string | null;
};

export type DhcpStaticLease = {
  section: string;
  hostname: string | null;
  ip: string | null;
  mac: string | null;
  enabled: boolean;
};

export type DhcpInfo = {
  pools: DhcpPool[];
  leases: DhcpLease[];
  static_leases: DhcpStaticLease[];
  enabled: boolean;
  gateway: string | null;
  dns: string[];
  domain: string | null;
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

export type ServiceInfo = {
  name: string;
  running: boolean;
  enabled: boolean;
  configured: boolean;
  version: string | null;
  detail: string | null;
};

export type DeviceSnapshot = {
  meta: SnapshotMeta;
  cpu: CpuInfo | null;
  memory: MemoryInfo | null;
  temperature: TemperatureReading[];
  storage: StorageMount[];
  network: NetworkInterface[];
  network_status: NetworkStatus | null;
  firewall: FirewallInfo;
  wifi: WifiInfo;
  clients: DhcpLease[];
  arp: ArpEntry[];
  neighbors: NeighborEntry[];
  routing: RouteEntry[];
  vpn: VpnTunnel[];
  dhcp: DhcpInfo;
  packages: unknown[];
  services: ServiceInfo[];
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
