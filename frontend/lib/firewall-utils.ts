import type { FirewallZone as DashboardZone } from "@/lib/dashboard";
import type {
  FirewallZone as ManagementZone,
} from "@/lib/router-management";

/**
 * True when a version string is actually usage/help text. OpenWrt 25.12's fw4
 * treats ``-v`` as a *verbose* flag and prints ``Usage:`` (exit 0) instead of a
 * version, so both collectors can surface a bogus "version".
 */
export function isBogusVersion(version: string | null | undefined): boolean {
  if (!version) {
    return true;
  }
  const value = version.trim().toLowerCase();
  return !value || value.startsWith("usage");
}

/** A real version string, or ``null`` when the value is usage/help text. */
export function sanitizeVersion(
  version: string | null | undefined,
): string | null {
  if (isBogusVersion(version)) {
    return null;
  }
  return (version ?? "").trim() || null;
}

/**
 * The management firewall endpoint parses ``uci show firewall`` with a regex
 * that drops single-line list options (``network='wan' 'wan6'``), so a zone
 * with multiple networks reports no networks. The snapshot pipeline parses
 * them correctly; fill the management zone's missing networks from the
 * snapshot zone with the same name.
 */
export function mergeZoneNetworks(
  zones: ManagementZone[],
  snapshotZones: DashboardZone[],
): ManagementZone[] {
  return zones.map((zone) => {
    const present = Array.isArray(zone.network)
      ? zone.network.length > 0
      : Boolean(zone.network);
    if (present) {
      return zone;
    }
    const snapshot = snapshotZones.find((entry) => entry.name === zone.name);
    if (snapshot && snapshot.network.length > 0) {
      return { ...zone, network: snapshot.network };
    }
    return zone;
  });
}
