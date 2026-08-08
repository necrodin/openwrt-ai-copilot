"use client";

import { ArrowRight } from "lucide-react";

import type { FirewallForward } from "@/lib/router-management";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { EmptyState } from "@/components/dashboard/widget";

type Props = {
  forwardings: FirewallForward[];
  busy?: boolean;
  onToggle: (section: string, enabled: boolean) => void;
};

export function FirewallForwarding({ forwardings, busy = false, onToggle }: Props) {
  if (forwardings.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No zone-to-zone forwarding configured." />
      </div>
    );
  }

  return (
    <ul className="space-y-2">
      {forwardings.map((forward) => (
        <li
          key={forward.section}
          className={`rounded-md border px-4 py-3 ${forward.enabled ? "" : "opacity-60"}`}
        >
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0 space-y-0.5">
              <div className="flex flex-wrap items-center gap-2">
                <span className="truncate text-sm font-medium">
                  {forward.name || "Unnamed forwarding"}
                </span>
                <Badge variant={forward.enabled ? "default" : "secondary"}>
                  {forward.enabled ? "enabled" : "disabled"}
                </Badge>
                {forward.family ? <Badge variant="outline">{forward.family}</Badge> : null}
              </div>
              <p className="flex flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                <span className="font-medium">{forward.src ?? "any"}</span>
                <ArrowRight className="size-3" aria-hidden />
                <span className="font-medium">{forward.dest ?? "any"}</span>
                <span className="text-muted-foreground">·</span>
                <code className="font-mono">{forward.section}</code>
              </p>
            </div>
            <Button
              size="sm"
              variant={forward.enabled ? "outline" : "default"}
              disabled={busy}
              onClick={() => onToggle(forward.section, !forward.enabled)}
            >
              {forward.enabled ? "Disable" : "Enable"}
            </Button>
          </div>
        </li>
      ))}
    </ul>
  );
}