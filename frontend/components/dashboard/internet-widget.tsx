import { Wifi } from "lucide-react";

import type { DeviceSnapshot } from "@/lib/dashboard";
import { isWan } from "@/lib/dashboard-utils";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { Widget, EmptyState } from "@/components/dashboard/widget";

type Props = {
  snapshot: DeviceSnapshot | null;
  loading?: boolean;
  error?: string | null;
};

type Status = {
  label: string;
  variant: "default" | "destructive" | "warn";
  detail: string;
};

function internetStatus(snapshot: DeviceSnapshot): Status {
  const defaultV4 = snapshot.routing.some(
    (route) =>
      route.family === "ipv4" &&
      (route.destination === "0.0.0.0/0" || route.destination === "default"),
  );
  const wan = snapshot.network.find((iface) => isWan(iface));
  const wanIp = wan?.addresses.find((address) => address.family === "ipv4")?.address;
  const gateway = defaultV4
    ? snapshot.routing.find((route) => route.destination === "0.0.0.0/0")?.gateway
    : null;

  if (!defaultV4) {
    return {
      label: "Offline",
      variant: "destructive",
      detail: "No default route configured",
    };
  }
  if (!wan?.up || !wanIp) {
    return {
      label: "Degraded",
      variant: "warn",
      detail: "Default route present, but the WAN has no address",
    };
  }
  return {
    label: "Online",
    variant: "default",
    detail: `WAN ${wanIp} · via ${gateway ?? "gateway"}`,
  };
}

export function InternetWidget({ snapshot, loading = false, error = null }: Props) {
  if (snapshot === null) {
    return (
      <Widget title="Internet" icon={Wifi} loading={loading} error={error}>
        <EmptyState message="Waiting for network data." />
      </Widget>
    );
  }
  const status = internetStatus(snapshot);
  const kernel = snapshot.kernel;
  const distribution = kernel.distribution || "OpenWrt";
  const version = kernel.release_version || kernel.release || null;
  const target = kernel.target || null;
  const revision = kernel.revision || null;
  const build = kernel.build_date || null;

  return (
    <Widget
      title="Internet"
      icon={Wifi}
      subtitle={kernel.model || kernel.board || "router"}
      loading={loading}
      error={error}
    >
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <Badge
            className={cn(
              status.variant === "warn" && "border-amber-500 bg-amber-500/15 text-amber-600",
            )}
            variant={status.variant === "warn" ? "outline" : status.variant}
          >
            {status.label}
          </Badge>
          <span className="text-xs font-medium text-muted-foreground">
            {distribution}
            {version ? ` ${version}` : ""}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">{status.detail}</p>
        {target || revision || build ? (
          <dl className="space-y-0.5 text-xs text-muted-foreground">
            {target ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="shrink-0 font-medium">Target:</dt>
                <dd className="truncate">{target}</dd>
              </div>
            ) : null}
            {revision ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="shrink-0 font-medium">Revision:</dt>
                <dd className="truncate font-mono">{revision}</dd>
              </div>
            ) : null}
            {build ? (
              <div className="flex items-baseline gap-1.5">
                <dt className="shrink-0 font-medium">Build:</dt>
                <dd className="truncate">{build}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
        {snapshot.network_status ? (
          <div className="space-y-1 text-xs text-muted-foreground">
            {snapshot.network_status.gateway ? (
              <p>
                <span className="font-medium">Gateway:</span>{" "}
                {snapshot.network_status.gateway}
              </p>
            ) : null}
            {snapshot.network_status.dns.length > 0 ? (
              <p className="truncate">
                <span className="font-medium">DNS:</span>{" "}
                {snapshot.network_status.dns.join(" · ")}
              </p>
            ) : null}
            {snapshot.network_status.wan_interface ? (
              <p>
                <span className="font-medium">Uplink:</span>{" "}
                {snapshot.network_status.wan_interface}
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </Widget>
  );
}
