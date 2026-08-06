"use client";

import type { FirewallNat } from "@/lib/dashboard";
import { Badge } from "@/components/ui/badge";
import { EmptyState } from "@/components/dashboard/widget";
import { PolicyBadge } from "@/components/firewall/policy-badge";

type Props = {
  rules: FirewallNat[];
};

export function FirewallNatTable({ rules }: Props) {
  if (rules.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No custom NAT rules configured." />
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {rules.map((rule) => (
        <li
          key={rule.section}
          className={`rounded-md border px-4 py-3 ${rule.enabled ? "" : "opacity-60"}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium">
                  {rule.name || "Unnamed NAT rule"}
                </span>
                <Badge variant={rule.enabled ? "default" : "secondary"}>
                  {rule.enabled ? "enabled" : "disabled"}
                </Badge>
                {rule.proto ? <Badge variant="outline">{rule.proto}</Badge> : null}
              </div>
              <p className="text-xs text-muted-foreground">
                {[rule.src, rule.dest_ip, rule.dest, rule.family]
                  .filter(Boolean)
                  .join(" · ") || "All traffic"}{" "}
                · <code className="font-mono">{rule.section}</code>
              </p>
            </div>
            {rule.target ? <PolicyBadge value={rule.target} /> : null}
          </div>
        </li>
      ))}
    </ul>
  );
}