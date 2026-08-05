import type { LucideIcon } from "lucide-react";

import type { NetworkInterface } from "@/lib/dashboard";
import { formatBytes } from "@/lib/dashboard-utils";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  title: string;
  icon: LucideIcon;
  interfaces: NetworkInterface[];
  subtitle?: string;
  className?: string;
  loading?: boolean;
  error?: string | null;
};

export function InterfaceWidget({
  title,
  icon,
  interfaces,
  subtitle,
  className,
  loading = false,
  error = null,
}: Props) {
  if (interfaces.length === 0) {
    return (
      <Widget title={title} icon={icon} className={className} loading={loading} error={error}>
        <EmptyState message={`No ${title.toLowerCase()} interface detected.`} />
      </Widget>
    );
  }

  return (
    <Widget
      title={title}
      icon={icon}
      subtitle={subtitle ?? `${interfaces.length} interface${interfaces.length > 1 ? "s" : ""}`}
      className={className}
      loading={loading}
      error={error}
    >
      <ul className="space-y-3">
        {interfaces.map((iface, index) => {
          const ipv4 = iface.addresses.find((address) => address.family === "ipv4");
          const ipv6 = iface.addresses.find((address) => address.family === "ipv6");
          return (
            <li
              key={`${iface.name}-${iface.device ?? ""}-${index}`}
              className="space-y-2"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="flex items-center gap-2 font-medium">
                  {iface.name}
                  {iface.is_bridge ? <Badge variant="outline">bridge</Badge> : null}
                  {iface.vlan_id != null ? (
                    <Badge variant="outline">VLAN {iface.vlan_id}</Badge>
                  ) : null}
                </span>
                <Badge variant={iface.up ? "default" : "secondary"}>
                  {iface.up ? "Up" : "Down"}
                </Badge>
              </div>
              <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">IPv4</dt>
                  <dd className="truncate tabular-nums">
                    {ipv4 ? ipv4.address : "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Link</dt>
                  <dd className="tabular-nums">
                    {iface.link === true ? "Up" : iface.link === false ? "Down" : "—"}
                    {iface.speed_mbps ? ` @ ${iface.speed_mbps} Mbps` : ""}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">MAC</dt>
                  <dd className="truncate font-mono text-xs">
                    {iface.mac ?? "—"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">MTU</dt>
                  <dd className="tabular-nums">{iface.mtu ?? "—"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Received</dt>
                  <dd className="tabular-nums">{formatBytes(iface.rx_bytes)}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Sent</dt>
                  <dd className="tabular-nums">{formatBytes(iface.tx_bytes)}</dd>
                </div>
              </dl>
              {iface.gateway || ipv6 ? (
                <p className="text-xs text-muted-foreground">
                  {iface.gateway ? `gw ${iface.gateway}` : ""}
                  {iface.gateway && ipv6 ? " · " : ""}
                  {ipv6 ? ipv6.address : ""}
                  {iface.device ? ` · ${iface.device}` : ""}
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Widget>
  );
}
