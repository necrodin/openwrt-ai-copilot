"use client";

import { useMemo, useState } from "react";
import { Search, X } from "lucide-react";

import type { DhcpLease } from "@/lib/dashboard";
import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Props = {
  leases: DhcpLease[];
};

export function DhcpLeases({ leases }: Props) {
  const [search, setSearch] = useState("");

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) {
      return leases;
    }
    return leases.filter((lease) =>
      [lease.hostname, lease.ip, lease.mac, lease.interface]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(needle)),
    );
  }, [leases, search]);

  return (
    <div className="space-y-3">
      <div className="relative w-full md:max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type="search"
          placeholder="Search leases…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="pl-9 pr-8"
          aria-label="Search active leases"
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

      {visible.length === 0 ? (
        <div className="rounded-xl border py-10">
          <EmptyState message="No active leases match your search." />
        </div>
      ) : (
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[560px] text-left text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">Hostname</th>
                <th className="px-3 py-2 font-medium">IP</th>
                <th className="px-3 py-2 font-medium">MAC</th>
                <th className="px-3 py-2 font-medium">Expires</th>
                <th className="px-3 py-2 font-medium">Interface</th>
              </tr>
            </thead>
            <tbody>
              {visible.map((lease) => (
                <tr key={`${lease.mac ?? lease.ip}:${lease.ip}`} className="border-b last:border-0">
                  <td className="px-3 py-2 font-medium">{lease.hostname || "—"}</td>
                  <td className="px-3 py-2 font-mono text-xs">{lease.ip}</td>
                  <td className="px-3 py-2 font-mono text-xs">{lease.mac ?? "—"}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{lease.expires ?? "—"}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{lease.interface ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}