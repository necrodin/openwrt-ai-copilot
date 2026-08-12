import type {
  ArpEntry,
  DeviceSnapshot,
  DhcpLease,
  NeighborEntry,
  WifiClient,
} from "@/lib/dashboard";

export type ClientConnection = "online" | "offline";

export type ClientMedium = "wired" | "wireless" | "unknown";

export type ClientSource = "dhcp" | "arp" | "wifi" | "neighbor";

/**
 * A single device on the network, merged across every source the snapshot
 * exposes (DHCP leases, ARP, WiFi stations, IPv6 neighbor cache). One MAC is
 * one client; entries without a MAC are keyed by their IP instead.
 */
export type NetworkClient = {
  id: string;
  hostname: string | null;
  mac: string | null;
  ipv4: string | null;
  ipv6: string | null;
  interface: string | null;
  vendor: string | null;
  medium: ClientMedium;
  online: boolean;
  signal_dbm: number | null;
  rx_bytes: number | null;
  tx_bytes: number | null;
  connected_minutes: number | null;
  ssid: string | null;
  lease_expires: string | null;
  lease_active: boolean | null;
  arp_state: string | null;
  last_seen: string | null;
  sources: ClientSource[];
};

export type ClientFilter = {
  search: string;
  connection: ClientConnection | "all";
  medium: ClientMedium | "all";
};

export type ClientSortKey =
  | "name"
  | "ip"
  | "mac"
  | "signal"
  | "last-seen"
  | "online";

const ARP_REACHABLE = new Set(["complete", "reachable", "REACHABLE"]);
const WIRELESS_IFACE = /^(phy|wlan|wl|wifi|radio|ra|rai)[0-9a-z-]*$/i;
const WIRED_IFACE = /^(eth|en|ppp|wwan|wan[0-9]?|lan[0-9]|usb|ge?|x?gbe)[0-9a-z.-]*$/i;

function normalizeMac(mac: string | null | undefined): string | null {
  if (!mac) {
    return null;
  }
  const stripped = mac.toLowerCase().replace(/[:-]/g, "");
  return /^[0-9a-f]{12}$/.test(stripped) ? stripped : mac.toLowerCase();
}

function isLeaseActive(expires: string | null, nowMs: number): boolean {
  if (!expires) {
    return true;
  }
  const epochSeconds = Number(expires);
  if (Number.isFinite(epochSeconds)) {
    return epochSeconds > nowMs / 1000;
  }
  return true;
}

/** Bridge topology lookup derived from the snapshot's network interfaces. */
type BridgeLookup = {
  /** Logical interface name -> underlying device (e.g. ``lan`` -> ``br-lan``). */
  logicalDevice: Map<string, string>;
  /** Bridge name/device -> member interfaces. */
  members: Map<string, string[]>;
};

function buildBridgeLookup(snapshot: DeviceSnapshot): BridgeLookup {
  const logicalDevice = new Map<string, string>();
  const members = new Map<string, string[]>();
  for (const iface of snapshot.network) {
    if (iface.device) {
      logicalDevice.set(iface.name, iface.device);
    }
    if (!iface.is_bridge && !iface.name.startsWith("br-")) {
      continue;
    }
    const memberList = iface.bridge_members ?? [];
    if (memberList.length === 0) {
      continue;
    }
    const add = (key: string) => {
      members.set(key, [...(members.get(key) ?? []), ...memberList]);
    };
    add(iface.name);
    if (iface.device && iface.device !== iface.name) {
      add(iface.device);
    }
  }
  return { logicalDevice, members };
}

function memberMedium(member: string): ClientMedium {
  if (WIRELESS_IFACE.test(member)) {
    return "wireless";
  }
  if (WIRED_IFACE.test(member)) {
    return "wired";
  }
  return "unknown";
}

function classifyMedium(
  inWifi: boolean,
  iface: string | null,
  bridge: BridgeLookup,
): ClientMedium {
  if (inWifi) {
    return "wireless";
  }
  if (!iface) {
    return "unknown";
  }
  if (WIRELESS_IFACE.test(iface)) {
    return "wireless";
  }
  if (WIRED_IFACE.test(iface)) {
    return "wired";
  }
  // The interface is a logical/bridge name (``lan``/``br-lan``) whose actual
  // medium depends on the bridge members. Never guess wired by default.
  const resolved = bridge.logicalDevice.get(iface) ?? iface;
  const memberList = bridge.members.get(resolved) ?? bridge.members.get(iface);
  if (memberList && memberList.length > 0) {
    const media = new Set(memberList.map(memberMedium));
    if (media.size === 1) {
      const only = [...media][0];
      if (only === "wireless" || only === "wired") {
        return only;
      }
    }
  }
  return "unknown";
}

type MergeKey =
  | "hostname"
  | "mac"
  | "ipv4"
  | "ipv6"
  | "interface"
  | "signal_dbm"
  | "rx_bytes"
  | "tx_bytes"
  | "connected_minutes"
  | "ssid"
  | "lease_expires"
  | "arp_state";

type MergeState = {
  key: string;
  sources: Set<ClientSource>;
  values: Partial<Record<MergeKey, unknown>>;
};

export function buildClients(
  snapshot: DeviceSnapshot | null,
  nowIso: string | null,
): NetworkClient[] {
  if (snapshot === null) {
    return [];
  }

  const nowMs = nowIso ? new Date(nowIso).getTime() : Date.now();
  const byKey = new Map<string, MergeState>();
  const byIpv4 = new Map<string, string>();
  const byIpv6 = new Map<string, string>();
  const bridge = buildBridgeLookup(snapshot);

  const merge = (
    key: string,
    source: ClientSource,
    values: Partial<Record<MergeKey, unknown>>,
  ) => {
    const existing = byKey.get(key);
    if (existing) {
      existing.sources.add(source);
      existing.values = { ...existing.values, ...values };
    } else {
      byKey.set(key, { key, sources: new Set([source]), values });
    }
  };

  const addV4 = (state: MergeState, ip: string) => byIpv4.set(ip, state.key);
  const addV6 = (state: MergeState, ip: string) => byIpv6.set(ip, state.key);

  for (const lease of snapshot.clients as DhcpLease[]) {
    const macKey = normalizeMac(lease.mac);
    if (macKey) {
      merge(macKey, "dhcp", {
        hostname: lease.hostname || undefined,
        ipv4: lease.ip,
        mac: lease.mac,
        interface: lease.interface,
        lease_expires: lease.expires,
      });
    } else {
      merge(lease.ip, "dhcp", {
        hostname: lease.hostname || undefined,
        ipv4: lease.ip,
        interface: lease.interface,
        lease_expires: lease.expires,
      });
    }
  }

  for (const entry of snapshot.arp as ArpEntry[]) {
    const macKey = normalizeMac(entry.mac);
    const values = {
      ipv4: entry.ip,
      mac: entry.mac,
      interface: entry.interface,
      arp_state: entry.state,
    };
    if (macKey) {
      merge(macKey, "arp", values);
    } else {
      merge(entry.ip, "arp", values);
    }
  }

  for (const client of snapshot.wifi.clients as WifiClient[]) {
    const macKey = normalizeMac(client.mac);
    if (macKey) {
      merge(macKey, "wifi", {
        mac: client.mac,
        signal_dbm: client.signal_dbm,
        rx_bytes: client.rx_bytes,
        tx_bytes: client.tx_bytes,
        connected_minutes: client.connected_minutes,
        ssid: client.ssid,
      });
    }
  }

  for (const entry of (snapshot.neighbors ?? []) as NeighborEntry[]) {
    const macKey = normalizeMac(entry.mac);
    const values = {
      ipv6: entry.ip,
      mac: entry.mac,
      interface: entry.interface,
    };
    if (macKey) {
      merge(macKey, "neighbor", values);
    } else {
      merge(entry.ip, "neighbor", values);
    }
  }

  // Index IPv6/IPv4 lookups so clients keyed on one family can pick up the
  // other family's addresses without a matching MAC.
  for (const state of byKey.values()) {
    const ipv4 = state.values.ipv4 as string | undefined;
    const ipv6 = state.values.ipv6 as string | undefined;
    if (ipv4) {
      addV4(state, ipv4);
    }
    if (ipv6) {
      addV6(state, ipv6);
    }
  }

  const clients: NetworkClient[] = [];
  for (const state of byKey.values()) {
    const v = state.values;
    const mac = (v.mac as string | null) ?? null;
    const ipv4 = (v.ipv4 as string | null) ?? byIpv4.get(state.key) ?? null;
    const ipv6 = (v.ipv6 as string | null) ?? byIpv6.get(state.key) ?? null;
    const inWifi = state.sources.has("wifi");
    const arpState = (v.arp_state as string | null) ?? null;
    const arpReachable = arpState !== null && ARP_REACHABLE.has(arpState);
    const leaseExpires = (v.lease_expires as string | null) ?? null;
    const leaseActive =
      v.lease_expires !== undefined ? isLeaseActive(leaseExpires, nowMs) : null;
    const macKey = normalizeMac(mac);
    const agentMedium = macKey ? snapshot.client_media?.[macKey] : undefined;

    clients.push({
      id: mac ?? ipv4 ?? ipv6 ?? "unknown",
      hostname: (v.hostname as string | null) ?? null,
      mac,
      ipv4,
      ipv6,
      interface: (v.interface as string | null) ?? null,
      vendor: null,
      medium:
        agentMedium ?? classifyMedium(inWifi, (v.interface as string | null) ?? null, bridge),
      online: inWifi || arpReachable,
      signal_dbm: (v.signal_dbm as number | null) ?? null,
      rx_bytes: (v.rx_bytes as number | null) ?? null,
      tx_bytes: (v.tx_bytes as number | null) ?? null,
      connected_minutes: (v.connected_minutes as number | null) ?? null,
      ssid: (v.ssid as string | null) ?? null,
      lease_expires: leaseExpires,
      lease_active: leaseActive,
      arp_state: arpState,
      last_seen: null,
      sources: [...state.sources].sort(),
    });
  }

  return clients;
}

export function filterClients(clients: NetworkClient[], filter: ClientFilter): NetworkClient[] {
  const needle = filter.search.trim().toLowerCase();
  return clients.filter((client) => {
    if (filter.connection !== "all" && client.online !== (filter.connection === "online")) {
      return false;
    }
    if (filter.medium !== "all" && client.medium !== filter.medium) {
      return false;
    }
    if (needle === "") {
      return true;
    }
    const haystack = [
      client.hostname,
      client.mac,
      client.ipv4,
      client.ipv6,
      client.interface,
      client.ssid,
      client.vendor,
    ]
      .filter(Boolean)
      .join(" ")
      .toLowerCase();
    return haystack.includes(needle);
  });
}

function compareIp(a: string | null, b: string | null): number {
  const partsOf = (ip: string | null): number[] | null => {
    if (!ip || ip.includes(":")) {
      return null;
    }
    return ip.split(".").map((part) => Number.parseInt(part, 10) || 0);
  };
  const av = partsOf(a);
  const bv = partsOf(b);
  if (av === null && bv === null) {
    return (a ?? "").localeCompare(b ?? "");
  }
  if (av === null) {
    return 1;
  }
  if (bv === null) {
    return -1;
  }
  for (let i = 0; i < 4; i += 1) {
    if (av[i] !== bv[i]) {
      return av[i] - bv[i];
    }
  }
  return 0;
}

export function sortClients(clients: NetworkClient[], key: ClientSortKey): NetworkClient[] {
  const sorted = [...clients];
  switch (key) {
    case "name":
      sorted.sort((a, b) =>
        (a.hostname ?? a.mac ?? "").localeCompare(b.hostname ?? b.mac ?? "", undefined, {
          numeric: true,
        }),
      );
      break;
    case "ip":
      sorted.sort((a, b) => compareIp(a.ipv4, b.ipv4) || compareIp(a.ipv6, b.ipv6));
      break;
    case "mac":
      sorted.sort((a, b) => (a.mac ?? "").localeCompare(b.mac ?? ""));
      break;
    case "signal":
      sorted.sort((a, b) => (b.signal_dbm ?? -Infinity) - (a.signal_dbm ?? -Infinity));
      break;
    case "last-seen":
      sorted.sort((a, b) => (b.last_seen ?? "").localeCompare(a.last_seen ?? ""));
      break;
    case "online":
      sorted.sort((a, b) => Number(b.online) - Number(a.online));
      break;
  }
  return sorted;
}
