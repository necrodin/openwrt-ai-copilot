"use client";

import { Search, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { FirewallRule } from "@/lib/router-management";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { EmptyState } from "@/components/dashboard/widget";
import { PolicyBadge } from "@/components/firewall/policy-badge";

type Props = {
  rules: FirewallRule[];
  busy?: boolean;
  onToggle: (section: string, enabled: boolean) => void;
};

function ruleSummary(rule: FirewallRule): string {
  const parts: string[] = [];
  if (rule.src) {
    parts.push(`from ${rule.src}`);
  }
  if (rule.dest) {
    parts.push(`to ${rule.dest}`);
  }
  if (rule.proto) {
    parts.push(rule.proto);
  }
  if (rule.src_port) {
    parts.push(`src port ${rule.src_port}`);
  }
  if (rule.dest_port) {
    parts.push(`port ${rule.dest_port}`);
  }
  return parts.join(" · ") || "All traffic";
}

export function FirewallRules({ rules, busy = false, onToggle }: Props) {
  const [search, setSearch] = useState("");

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) {
      return rules;
    }
    return rules.filter((rule) =>
      [rule.name, rule.src, rule.dest, rule.proto, rule.target, rule.section, rule.dest_port]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(needle)),
    );
  }, [rules, search]);

  return (
    <div className="space-y-3">
      <div className="relative w-full md:max-w-sm">
        <Search
          className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
          aria-hidden
        />
        <Input
          type="search"
          placeholder="Search rules…"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
          className="pl-9 pr-8"
          aria-label="Search firewall rules"
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
          <EmptyState message="No firewall rules match your search." />
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((rule) => (
            <li
              key={rule.section}
              className={`rounded-md border px-4 py-3 ${
                rule.enabled ? "" : "opacity-60"
              }`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 space-y-0.5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {rule.name || "Unnamed rule"}
                    </span>
                    <Badge variant={rule.enabled ? "default" : "secondary"}>
                      {rule.enabled ? "enabled" : "disabled"}
                    </Badge>
                    {rule.family ? (
                      <Badge variant="outline">{rule.family}</Badge>
                    ) : null}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {ruleSummary(rule)} · <code className="font-mono">{rule.section}</code>
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <PolicyBadge value={rule.target} />
                  <Button
                    size="sm"
                    variant={rule.enabled ? "outline" : "default"}
                    disabled={busy}
                    onClick={() => onToggle(rule.section, !rule.enabled)}
                  >
                    {rule.enabled ? "Disable" : "Enable"}
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}