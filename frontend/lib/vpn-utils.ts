import type { VpnTunnel } from "@/lib/dashboard";
import type { StatusBadgeTone } from "@/components/ui/status-badge";

export type TunnelStatus = { label: string; tone: StatusBadgeTone };

/**
 * Distinct tunnel state: a tunnel is "Up" only when runtime state says so; a
 * configured-but-inactive tunnel is "Configured", a disabled one "Disabled",
 * and an unknown case is "Down". A configured-but-not-running tunnel is never
 * shown as active.
 */
export function tunnelStatus(tunnel: VpnTunnel): TunnelStatus {
  if (tunnel.up) {
    return { label: "Up", tone: "success" };
  }
  if (tunnel.detail?.state === "configured-but-inactive" && tunnel.enabled) {
    return { label: "Configured", tone: "warning" };
  }
  if (!tunnel.enabled) {
    return { label: "Disabled", tone: "neutral" };
  }
  return { label: "Down", tone: "neutral" };
}
