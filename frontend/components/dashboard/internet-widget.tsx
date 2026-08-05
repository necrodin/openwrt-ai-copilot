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
          <span className="text-xs text-muted-foreground">
            {kernel.kernel ? `OpenWrt ${kernel.kernel}` : "OpenWrt"}
            {kernel.release ? ` · ${kernel.release}` : ""}
          </span>
        </div>
        <p className="text-sm text-muted-foreground">{status.detail}</p>
      </div>
    </Widget>
  );
}
