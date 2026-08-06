"use client";

import { Search, SortAsc, SortDesc, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { WifiNetwork } from "@/lib/dashboard";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/dashboard/widget";

type Props = {
  networks: WifiNetwork[];
  busy?: boolean;
  onToggle: (section: string, enabled: boolean) => void;
};

type SortKey = "ssid" | "radio" | "encryption" | "enabled" | "clients";

const SORT_OPTIONS: { value: SortKey; label: string }[] = [
  { value: "ssid", label: "SSID" },
  { value: "radio", label: "Radio" },
  { value: "encryption", label: "Encryption" },
  { value: "enabled", label: "Status" },
  { value: "clients", label: "Clients" },
];

export function WirelessNetworks({ networks, busy = false, onToggle }: Props) {
  const [search, setSearch] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("ssid");
  const [ascending, setAscending] = useState(true);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    const filtered = needle
      ? networks.filter((network) =>
          [network.ssid, network.radio, network.interface, network.encryption, network.network]
            .filter(Boolean)
            .some((value) => value?.toLowerCase().includes(needle)),
        )
      : networks;
    const sorted = [...filtered].sort((a, b) => {
      let result = 0;
      switch (sortKey) {
        case "ssid":
          result = a.ssid.localeCompare(b.ssid, undefined, { numeric: true });
          break;
        case "radio":
          result = a.radio.localeCompare(b.radio, undefined, { numeric: true });
          break;
        case "encryption":
          result = (a.encryption ?? "").localeCompare(b.encryption ?? "");
          break;
        case "enabled":
          result = Number(b.enabled) - Number(a.enabled);
          break;
        case "clients":
          result = a.client_count - b.client_count;
          break;
      }
      return ascending ? result : -result;
    });
    return sorted;
  }, [networks, search, sortKey, ascending]);

  const SortIcon = ascending ? SortAsc : SortDesc;

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center">
        <div className="relative w-full md:max-w-sm">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            placeholder="Search SSIDs…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9 pr-8"
            aria-label="Search SSIDs"
          />
          {search ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-0 right-0 size-9"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <X className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs font-medium text-muted-foreground">Sort</span>
          {SORT_OPTIONS.map((option) => (
            <Button
              key={option.value}
              type="button"
              size="sm"
              variant={sortKey === option.value ? "default" : "outline"}
              onClick={() => setSortKey(option.value)}
            >
              {option.label}
            </Button>
          ))}
          <Button
            type="button"
            size="sm"
            variant="ghost"
            onClick={() => setAscending((value) => !value)}
            aria-label="Toggle sort direction"
          >
            <SortIcon
              className={`size-4 ${ascending ? "text-emerald-500" : "text-amber-500"}`}
            />
          </Button>
        </div>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-xl border py-10">
          <EmptyState message="No wireless networks match your search." />
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((network) => (
            <li
              key={network.section || `${network.radio}-${network.ssid}`}
              className={`rounded-md border px-4 py-3 ${network.enabled ? "" : "opacity-60"}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {network.ssid || "Unnamed network"}
                    </span>
                    {network.hidden ? <Badge variant="outline">hidden</Badge> : null}
                    <Badge variant={network.enabled ? "default" : "secondary"}>
                      {network.enabled ? "enabled" : "disabled"}
                    </Badge>
                    {network.encryption ? (
                      <Badge variant="outline">{network.encryption}</Badge>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {network.interface ?? network.radio}
                    {network.mode ? ` · ${network.mode}` : ""}
                    {network.network ? ` · network ${network.network}` : ""}
                    {network.client_count ? ` · ${network.client_count} connected` : ""}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant={network.enabled ? "outline" : "default"}
                  disabled={busy}
                  onClick={() => onToggle(network.section, !network.enabled)}
                >
                  {network.enabled ? "Disable" : "Enable"}
                </Button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}