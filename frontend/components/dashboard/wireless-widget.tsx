import { Wifi } from "lucide-react";

import type { WifiInfo } from "@/lib/dashboard";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  wifi: WifiInfo;
  loading?: boolean;
  error?: string | null;
};

export function WirelessWidget({ wifi, loading = false, error = null }: Props) {
  if (wifi.radios.length === 0) {
    return (
      <Widget title="Wireless" icon={Wifi} loading={loading} error={error}>
        <EmptyState message="No wireless radios found." />
      </Widget>
    );
  }

  const totalStations = wifi.radios.reduce((sum, radio) => sum + radio.station_count, 0);

  return (
    <Widget
      title="Wireless"
      icon={Wifi}
      subtitle={`${wifi.clients.length} client${wifi.clients.length === 1 ? "" : "s"} connected`}
      loading={loading}
      error={error}
    >
      <ul className="space-y-2">
        {wifi.radios.map((radio) => (
          <li
            key={radio.name}
            className="flex items-center justify-between gap-3 rounded-md border px-3 py-2"
          >
            <div className="min-w-0">
              <p className="flex items-center gap-2 text-sm font-medium">
                <span className="truncate">{radio.ssid ?? radio.name}</span>
                {radio.band ? (
                  <Badge variant="outline">{radio.band}</Badge>
                ) : null}
              </p>
              <p className="truncate text-xs text-muted-foreground">
                {radio.frequency_mhz ? `${radio.frequency_mhz} MHz` : ""}
                {radio.channel ? ` · ch ${radio.channel}` : ""}
                {radio.tx_power ? ` · ${radio.tx_power} dBm` : ""}
              </p>
            </div>
            <div className="shrink-0 text-right">
              <span
                className={cn(
                  "rounded-md px-2 py-1 text-xs font-semibold",
                  radio.up
                    ? "bg-emerald-500 text-white"
                    : "bg-muted text-muted-foreground",
                )}
              >
                {radio.up ? `${radio.station_count} sta` : "Down"}
              </span>
            </div>
          </li>
        ))}
      </ul>
      {totalStations > 0 ? (
        <p className="mt-2 text-xs text-muted-foreground">
          {totalStations} station{totalStations === 1 ? "" : "s"} associated in total.
        </p>
      ) : null}
    </Widget>
  );
}
