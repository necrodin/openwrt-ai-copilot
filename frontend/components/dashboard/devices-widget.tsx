import { MonitorSmartphone } from "lucide-react";

import type { DeviceSnapshot, DhcpLease } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  snapshot: DeviceSnapshot | null;
  loading?: boolean;
  error?: string | null;
};

function connectedDevices(snapshot: DeviceSnapshot | null): DhcpLease[] {
  if (snapshot === null) {
    return [];
  }
  if (snapshot.clients.length > 0) {
    return snapshot.clients;
  }
  return snapshot.arp.map((entry) => ({
    hostname: "",
    ip: entry.ip,
    mac: entry.mac,
    expires: null,
    interface: entry.interface,
  }));
}

export function DevicesWidget({ snapshot, loading = false, error = null }: Props) {
  const devices = connectedDevices(snapshot);

  if (devices.length === 0) {
    return (
      <Widget
        title="Connected Devices"
        icon={MonitorSmartphone}
        className="lg:col-span-2"
        loading={loading}
        error={error}
      >
        <EmptyState message="No clients discovered yet." />
      </Widget>
    );
  }

  return (
    <Widget
      title="Connected Devices"
      icon={MonitorSmartphone}
      subtitle={`${devices.length} device${devices.length === 1 ? "" : "s"} on the network`}
      className="lg:col-span-2"
      loading={loading}
      error={error}
    >
      <div className="max-h-64 overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-xs text-muted-foreground">
              <th className="pb-2 pr-2 font-medium">Hostname</th>
              <th className="pb-2 pr-2 font-medium">IP</th>
              <th className="pb-2 pr-2 font-medium">MAC</th>
              <th className="pb-2 font-medium">Interface</th>
            </tr>
          </thead>
          <tbody>
            {devices.map((device, index) => (
              <tr key={`${device.mac ?? device.ip ?? "dev"}-${index}`} className="border-t">
                <td className="py-1.5 pr-2 font-medium">
                  {device.hostname || "—"}
                </td>
                <td className="py-1.5 pr-2 tabular-nums">{device.ip}</td>
                <td className={cn("py-1.5 pr-2 font-mono text-xs")}>
                  {device.mac ?? "—"}
                </td>
                <td className="py-1.5">{device.interface ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Widget>
  );
}
