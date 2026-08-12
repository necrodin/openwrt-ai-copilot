import type { DnsHost } from "@/lib/router-management";

/**
 * True for the local resolver stub (loopback) addresses. These are what
 * ``/etc/resolv.conf`` shows on a standard OpenWrt device (dnsmasq listening on
 * 127.0.0.1/::1) — they are the local forwarder, never the upstream resolvers.
 */
export function isLoopbackResolver(server: string): boolean {
  const value = server.trim().toLowerCase();
  if (value === "localhost" || value === "::1" || value === "::1%lo") {
    return true;
  }
  if (value.startsWith("127.")) {
    return true;
  }
  return false;
}

/** True for loopback or multicast addresses (e.g. ``ff02::1`` from /etc/hosts). */
export function isInternalAddress(ip: string): boolean {
  const value = ip.trim().toLowerCase();
  if (isLoopbackResolver(value)) {
    return true;
  }
  // IPv6 multicast (ff00::/8) — /etc/hosts ships ip6-allnodes/allrouters here.
  if (value.startsWith("ff")) {
    return true;
  }
  return false;
}

/** Deduplicate resolver addresses preserving first-seen order. */
export function dedupeResolvers(servers: string[]): string[] {
  const seen = new Set<string>();
  const result: string[] = [];
  for (const server of servers) {
    const value = server.trim();
    if (!value || seen.has(value)) {
      continue;
    }
    seen.add(value);
    result.push(value);
  }
  return result;
}

/**
 * The real upstream resolvers for the DNS page.
 *
 * The authoritative source is the live snapshot's ``network_status.dns``
 * (netifd's per-interface ``dns-server``), which is what the Dashboard shows.
 * The management endpoint's ``upstream`` comes from ``/etc/resolv.conf`` and
 * on OpenWrt only contains the local dnsmasq stub (127.0.0.1 / ::1) — that
 * stub is never upstream and is filtered out. When the snapshot has no DNS the
 * management resolv.conf data (minus the stub) is used as a fallback.
 */
export function reconcileUpstream(
  managementUpstream: string[],
  snapshotDns: string[] | null | undefined,
): string[] {
  const authoritative = (snapshotDns ?? []).filter(
    (server) => !isLoopbackResolver(server),
  );
  if (authoritative.length > 0) {
    return dedupeResolvers(authoritative);
  }
  return dedupeResolvers(
    managementUpstream.filter((server) => !isLoopbackResolver(server)),
  );
}

/**
 * Drop internal-only host entries (loopback / multicast) that the management
 * endpoint surfaces from a stock ``/etc/hosts`` file. Real static hosts are
 * returned unchanged.
 */
export function filterInternalHosts(hosts: DnsHost[]): DnsHost[] {
  return hosts.filter((host) => !isInternalAddress(host.ip));
}
