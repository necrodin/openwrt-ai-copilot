import { ArrowDown, ChevronsUpDown } from "lucide-react";

import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ClientSortKey, NetworkClient } from "@/lib/clients";
import { formatBytes } from "@/lib/dashboard-utils";

type Column = {
  key: ClientSortKey | null;
  label: string;
  className?: string;
};

const COLUMNS: Column[] = [
  { key: "name", label: "Hostname" },
  { key: "ip", label: "IP" },
  { key: null, label: "IPv6", className: "hidden xl:table-cell" },
  { key: "mac", label: "MAC", className: "hidden md:table-cell" },
  { key: null, label: "Interface", className: "hidden lg:table-cell" },
  { key: "signal", label: "Signal", className: "hidden lg:table-cell" },
  { key: null, label: "Traffic", className: "hidden lg:table-cell" },
  { key: "last-seen", label: "Last seen" },
];

type Props = {
  clients: NetworkClient[];
  selectedId: string | null;
  sortKey: ClientSortKey;
  onSort: (key: ClientSortKey) => void;
  onSelect: (id: string | null) => void;
};

function mediumLabel(client: NetworkClient): string {
  if (client.medium === "wireless") {
    return "Wireless";
  }
  if (client.medium === "wired") {
    return "Wired";
  }
  return "—";
}

export function ClientTable({
  clients,
  selectedId,
  sortKey,
  onSort,
  onSelect,
}: Props) {
  if (clients.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No clients match the current filters." />
      </div>
    );
  }

  return (
    <div className="overflow-x-auto rounded-xl border">
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b text-left text-xs text-muted-foreground">
            <th className="px-3 py-2.5 font-medium">Status</th>
            {COLUMNS.map((column) => (
              <th key={column.label} className={cn("px-3 py-2.5 font-medium", column.className)}>
                {column.key ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    className="-ml-2 h-6 gap-1 px-2 text-xs font-medium text-muted-foreground"
                    onClick={() => onSort(column.key as ClientSortKey)}
                  >
                    {column.label}
                    {sortKey === column.key ? (
                      <ArrowDown className="size-3" aria-hidden />
                    ) : (
                      <ChevronsUpDown className="size-3 opacity-60" aria-hidden />
                    )}
                  </Button>
                ) : (
                  column.label
                )}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {clients.map((client) => {
            const selected = client.id === selectedId;
            const label =
              client.hostname ??
              client.mac ??
              client.ipv4 ??
              client.ipv6 ??
              "Unknown device";
            const traffic =
              client.rx_bytes !== null || client.tx_bytes !== null
                ? `↓ ${formatBytes(client.rx_bytes)} ↑ ${formatBytes(client.tx_bytes)}`
                : "—";
            return (
              <tr
                key={client.id}
                className={cn(
                  "cursor-pointer border-b last:border-b-0 hover:bg-accent/40",
                  selected && "bg-accent/60",
                )}
                onClick={() => onSelect(selected ? null : client.id)}
              >
                <td className="px-3 py-2 align-middle">
                  <span className="flex items-center gap-2 whitespace-nowrap">
                    <span
                      className={cn(
                        "size-2 shrink-0 rounded-full",
                        client.online ? "bg-emerald-500" : "bg-muted-foreground/50",
                      )}
                      aria-hidden
                    />
                    <span className="hidden text-xs text-muted-foreground sm:inline">
                      {client.online ? "Online" : "Offline"} · {mediumLabel(client)}
                    </span>
                  </span>
                </td>
                <td className="max-w-40 truncate px-3 py-2 font-medium">{label}</td>
                <td className="px-3 py-2 tabular-nums">{client.ipv4 ?? "—"}</td>
                <td className="hidden truncate px-3 py-2 font-mono text-xs tabular-nums xl:table-cell">
                  {client.ipv6 ?? "—"}
                </td>
                <td className="hidden px-3 py-2 font-mono text-xs tabular-nums md:table-cell">
                  {client.mac ?? "—"}
                </td>
                <td className="hidden px-3 py-2 lg:table-cell">{client.interface ?? "—"}</td>
                <td className="hidden px-3 py-2 tabular-nums lg:table-cell">
                  {client.signal_dbm !== null ? `${client.signal_dbm} dBm` : "—"}
                </td>
                <td className="hidden px-3 py-2 tabular-nums lg:table-cell">{traffic}</td>
                <td className="whitespace-nowrap px-3 py-2 tabular-nums text-muted-foreground">
                  {client.last_seen
                    ? new Date(client.last_seen).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })
                    : "—"}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
