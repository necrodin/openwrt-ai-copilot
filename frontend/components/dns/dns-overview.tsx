"use client";

import { FileClock, Globe, Server, ShieldCheck } from "lucide-react";

import type { DnsInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";

type Props = {
  dns: DnsInfo;
};

function Row({ label, value }: { label: string; value: string | null | undefined }) {
  return (
    <div className="flex items-center justify-between gap-4 border-b py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="truncate text-sm font-medium">{value || "—"}</span>
    </div>
  );
}

export function DnsOverview({ dns }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardContent className="space-y-1">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Server className="size-4 text-muted-foreground" aria-hidden />
            DNSMASQ
          </p>
          <div className="space-y-1">
            <Row label="Status" value={dns.service.running ? "Running" : "Stopped"} />
            <Row label="Enabled" value={dns.service.enabled ? "Yes" : "No"} />
            <Row
              label="Local Domain"
              value={dns.domain ? `${dns.domain}` : null}
            />
            <Row
              label="Upstream Resolvers"
              value={dns.upstream.length ? dns.upstream.join(", ") : null}
            />
          </div>
        </CardContent>
      </Card>
      <Card>
        <CardContent className="space-y-1">
          <p className="mb-2 flex items-center gap-2 text-sm font-semibold">
            <Globe className="size-4 text-muted-foreground" aria-hidden />
            FORWARDING
          </p>
          <div className="space-y-1">
            <Row label="Override Servers" value={dns.servers.length ? dns.servers.join(", ") : null} />
            <Row label="Domain" value={dns.domain ?? null} />
          </div>
        </CardContent>
      </Card>

      <div className="flex flex-wrap items-center gap-4 rounded-xl border p-4 lg:col-span-2">
        <span className="flex items-center gap-2 text-sm">
          <ShieldCheck className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">Resolver</span>
        </span>
        <span
          className={`text-sm font-medium ${
            dns.service.running ? "text-emerald-600 dark:text-emerald-400" : "text-foreground"
          }`}
        >
          {dns.service.running ? "Ready" : "Stopped"}
        </span>
        <span className="flex items-center gap-1 text-sm">
          <Globe className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">Upstream</span>
          <span className="font-medium">{dns.upstream.length}</span>
        </span>
        <span className="flex items-center gap-1 text-sm">
          <FileClock className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">Static entries</span>
          <span className="font-medium">{dns.hosts.length}</span>
        </span>
        <span className="flex items-center gap-1 text-sm">
          <Server className="size-4 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">Override servers</span>
          <span className="font-medium">{dns.servers.length}</span>
        </span>
      </div>
    </div>
  );
}