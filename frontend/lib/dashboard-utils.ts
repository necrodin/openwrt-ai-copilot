import type {
  DashboardUpdate,
  NetworkInterface,
  Source,
} from "@/lib/dashboard";
import { API_BASE_URL } from "@/lib/api";
import { wsAuthQuery } from "@/lib/auth";

export type ConnectionStatus =
  | "connecting"
  | "live"
  | "reconnecting"
  | "offline";

const WAN_PROTOS = new Set([
  "dhcp",
  "dhcpv6",
  "pppoe",
  "ppp",
  "qmi",
  "wwan",
  "wwan6",
  "3g",
  "lte",
]);

export function isWan(iface: NetworkInterface): boolean {
  return (
    iface.name === "wan" ||
    iface.name.startsWith("wan") ||
    (iface.proto !== null && WAN_PROTOS.has(iface.proto))
  );
}

export function dashboardSocketUrl(): string {
  const wsPath = "/dashboard/ws";
  const protocol = () =>
    window.location.protocol === "https:" ? "wss" : "ws";
  let base: string;
  if (API_BASE_URL.startsWith("http")) {
    const url = new URL(API_BASE_URL);
    base = `${protocol()}://${url.host}${url.pathname.replace(/\/$/, "")}${wsPath}`;
  } else {
    base = `${protocol()}://${window.location.host}${API_BASE_URL}${wsPath}`;
  }
  const query = wsAuthQuery();
  return query ? `${base}?${query}` : base;
}

export function formatBytes(bytes: number | null | undefined): string {
  if (bytes === null || bytes === undefined || Number.isNaN(bytes)) {
    return "—";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function formatBitRate(bitsPerSecond: number): string {
  if (!Number.isFinite(bitsPerSecond) || bitsPerSecond < 0) {
    return "—";
  }
  const units = ["bps", "Kbps", "Mbps", "Gbps"];
  let value = bitsPerSecond;
  let unit = 0;
  while (value >= 1000 && unit < units.length - 1) {
    value /= 1000;
    unit += 1;
  }
  return `${value >= 100 ? Math.round(value) : value.toFixed(1)} ${units[unit]}`;
}

export function formatDuration(seconds: number): string {
  if (!Number.isFinite(seconds) || seconds < 0) {
    return "—";
  }
  const days = Math.floor(seconds / 86400);
  const hours = Math.floor((seconds % 86400) / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  if (days > 0) {
    return `${days}d ${hours}h`;
  }
  if (hours > 0) {
    return `${hours}h ${minutes}m`;
  }
  return `${minutes}m`;
}

export function ipv4PrefixToNetmask(prefix: number): string {
  const bits = Math.max(0, Math.min(32, Math.floor(prefix)));
  const mask = bits === 0 ? 0 : (~0 << (32 - bits)) >>> 0;
  return [
    (mask >>> 24) & 255,
    (mask >>> 16) & 255,
    (mask >>> 8) & 255,
    mask & 255,
  ].join(".");
}

export function interfaceAddresses(
  iface: NetworkInterface,
  family: "ipv4" | "ipv6",
): string[] {
  return iface.addresses
    .filter((address) => address.family === family && address.address)
    .map((address) => address.address);
}

/**
 * Honest label for the router's WAN IPv4 address. Only an address with
 * evidence of being globally public (``is_public === true``) is labelled
 * "Public IP"; a private/carrier-NAT/LAN address is simply the router's
 * assigned "WAN IP". Unknown stays conservative ("WAN IP") — we never claim
 * publicness we cannot prove.
 */
export function wanAddressLabel(isPublic: boolean | null | undefined): string {
  return isPublic === true ? "Public IP" : "WAN IP";
}

export function interfaceCidr(iface: NetworkInterface): string | null {
  const ipv4 = iface.addresses.find((address) => address.family === "ipv4" && address.address);
  if (!ipv4) {
    return null;
  }
  return `${ipv4.address}/${ipv4.prefix || 24}`;
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) {
    return "—";
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return date.toLocaleTimeString([], {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function sourceLabel(source: Source): string {
  switch (source) {
    case "ssh":
      return "SSH";
    case "local":
      return "Local";
    case "simulated":
      return "Demo";
    case "none":
      return "Not configured";
  }
}

export function parseUpdate(raw: string): DashboardUpdate | null {
  try {
    const parsed = JSON.parse(raw) as DashboardUpdate;
    if (parsed.type !== "update" || parsed.snapshot === null) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}
