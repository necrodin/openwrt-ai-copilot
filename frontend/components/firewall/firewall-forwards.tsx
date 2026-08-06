"use client";

import { ArrowRight } from "lucide-react";

import type { FirewallForward } from "@/lib/dashboard";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/dashboard/widget";
import { PolicyBadge } from "@/components/firewall/policy-badge";

type Props = {
  forwards: FirewallForward[];
};

export function FirewallForwards({ forwards }: Props) {
  if (forwards.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No port forwards configured." />
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {forwards.map((forward) => (
        <li
          key={forward.section}
          className={`rounded-md border px-4 py-3 ${forward.enabled ? "" : "opacity-60"}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium">
                  {forward.name || "Unnamed forward"}
                </span>
                <Badge variant={forward.enabled ? "default" : "secondary"}>
                  {forward.enabled ? "enabled" : "disabled"}
                </Badge>
                {forward.proto ? <Badge variant="outline">{forward.proto}</Badge> : null}
              </div>
              <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span className="font-mono">
                  {forward.src ?? "*"}
                  {forward.src_dport ? `:${forward.src_dport}` : ""}
                </span>
                <ArrowRight className="size-3" aria-hidden />
                <span className="font-mono">
                  {forward.dest_ip ?? forward.dest ?? "*"}
                  {forward.dest_port ? `:${forward.dest_port}` : ""}
                </span>
                {forward.src_ip ? (
                  <span className="text-muted-foreground">for {forward.src_ip}</span>
                ) : null}
                <span className="text-muted-foreground">·</span>
                <code className="font-mono">{forward.section}</code>
              </p>
            </div>
            {forward.target ? <PolicyBadge value={forward.target} /> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}