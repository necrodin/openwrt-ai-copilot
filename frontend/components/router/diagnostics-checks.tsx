import { ShieldCheck } from "lucide-react";

import type { DeviceSnapshot } from "@/lib/dashboard";
import { computeHealthScore } from "@/lib/health-score";
import { isWan } from "@/lib/dashboard-utils";
import { cn } from "@/lib/utils";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  snapshot: DeviceSnapshot | null;
  loading?: boolean;
  error?: string | null;
};

type CheckStatus = "ok" | "warn" | "bad" | "unknown";

type Check = {
  id: string;
  label: string;
  detail: string;
  status: CheckStatus;
};

const statusTone: Record<CheckStatus, string> = {
  ok: "bg-emerald-500 text-white",
  warn: "bg-amber-500 text-white",
  bad: "bg-red-500 text-white",
  unknown: "bg-muted text-muted-foreground",
};

const statusLabel: Record<CheckStatus, string> = {
  ok: "Pass",
  warn: "Warning",
  bad: "Fail",
  unknown: "Unknown",
};

/**
 * Readiness checklist for the Diagnostics tab. Each row is derived purely from
 * the snapshot the backend already collects — health score, storage use, peak
 * temperature, default gateway, DNS resolvers, internet reachability and
 * firmware/kernel build. Nothing here fabricates data.
 */
export function DiagnosticsChecks({ snapshot, loading = false, error = null }: Props) {
  if (snapshot === null) {
    return (
      <Widget title="System Checks" icon={ShieldCheck} loading={loading} error={error}>
        <EmptyState message="No snapshot to evaluate yet." />
      </Widget>
    );
  }

  const health = computeHealthScore(snapshot);
  const checks: Check[] = [];

  const healthStatus: CheckStatus =
    health === null
      ? "unknown"
      : health.tone === "excellent" || health.tone === "good"
        ? "ok"
        : health.tone === "fair"
          ? "warn"
          : "bad";

  checks.push({
    id: "health",
    label: "Router health",
    detail: health === null ? "No snapshot" : `${health.score}/100`,
    status: healthStatus,
  });

  const storageMax = Math.max(
    0,
    ...snapshot.storage
      .filter(
        (mount) =>
          !["squashfs", "erofs", "romfs"].includes(mount.filesystem.toLowerCase()) &&
          mount.mountpoint !== "/rom",
      )
      .map((mount) => mount.use_percent ?? 0),
  );
  const storageCount = snapshot.storage.length;
  checks.push({
    id: "storage",
    label: "Storage",
    detail:
      storageCount === 0
        ? "No mounts reported"
        : `Peak ${storageMax.toFixed(0)}% across ${storageCount} mount${storageCount === 1 ? "" : "s"}`,
    status: storageCount === 0 ? "unknown" : storageMax >= 90 ? "bad" : storageMax >= 75 ? "warn" : "ok",
  });

  const hottest = snapshot.temperature.reduce((max, t) => Math.max(max, t.temperature_c), 0);
  const tempCount = snapshot.temperature.length;
  checks.push({
    id: "temperature",
    label: "Temperature",
    detail: tempCount === 0 ? "No sensors" : `Peak ${hottest.toFixed(1)}°C`,
    status: tempCount === 0 ? "unknown" : hottest >= 75 ? "bad" : hottest >= 60 ? "warn" : "ok",
  });

  const gatewayIface = snapshot.network.find((iface) => iface.gateway != null);
  checks.push({
    id: "gateway",
    label: "Gateway",
    detail: gatewayIface?.gateway ?? "No default gateway detected",
    status: gatewayIface?.gateway != null ? "ok" : "bad",
  });

  const dns = snapshot.network_status?.dns ?? [];
  const dnsCount = dns.filter((d) => d && d.trim() !== "").length;
  checks.push({
    id: "dns",
    label: "DNS",
    detail: dnsCount > 0 ? `${dnsCount} resolver${dnsCount === 1 ? "" : "s"} configured` : "No DNS resolvers reported",
    status: dnsCount > 0 ? "ok" : "unknown",
  });

  const hasDefaultRoute = snapshot.routing.some(
    (route) =>
      route.family === "ipv4" &&
      (route.destination === "0.0.0.0/0" || route.destination === "default"),
  );
  const wanUp = snapshot.network.some((iface) => isWan(iface) && iface.up === true);
  const online = hasDefaultRoute && wanUp;
  checks.push({
    id: "internet",
    label: "Internet",
    detail: online ? "Default route up" : "No active uplink",
    status: online ? "ok" : "bad",
  });

  const metaFirmware = snapshot.meta.firmware;
  const kernelVersion = snapshot.kernel.version;
  const firmwareKnown = metaFirmware && metaFirmware.trim() !== "";
  checks.push({
    id: "firmware",
    label: "Firmware consistency",
    detail: firmwareKnown ? `${metaFirmware}${kernelVersion ? ` / ${kernelVersion}` : ""}` : "Firmware not detected",
    status: firmwareKnown ? "ok" : "unknown",
  });

  return (
    <Widget
      title="System Checks"
      icon={ShieldCheck}
      subtitle={`${checks.filter((check) => check.status === "ok").length} of ${checks.length} passing`}
      loading={loading}
      error={error}
    >
      <ul className="space-y-1">
        {checks.map((check) => (
          <li
            key={check.id}
            className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
          >
            <span className="truncate text-sm font-medium">{check.label}</span>
            <span className="flex items-center gap-2">
              <span className="truncate text-xs text-muted-foreground">{check.detail}</span>
              <span
                className={cn(
                  "shrink-0 rounded px-1.5 py-0.5 text-[11px] font-semibold",
                  statusTone[check.status],
                )}
              >
                {statusLabel[check.status]}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Widget>
  );
}