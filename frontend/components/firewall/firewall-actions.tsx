"use client";

import { RefreshCw, ShieldCheck } from "lucide-react";

import { Button } from "@/components/ui/button";

type Props = {
  busy?: boolean;
  onReload: () => void;
};

export function FirewallActions({ busy = false, onReload }: Props) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
      <div className="flex items-center gap-3">
        <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
          <ShieldCheck className="size-5 text-muted-foreground" aria-hidden />
        </span>
        <div className="min-w-0">
          <p className="text-sm font-medium">Reload firewall</p>
          <p className="text-xs text-muted-foreground">
            Apply the current configuration without dropping established connections.
          </p>
        </div>
      </div>
      <Button variant="outline" disabled={busy} onClick={onReload}>
        <RefreshCw className="size-4" aria-hidden />
        {busy ? "Reloading…" : "Reload"}
      </Button>
    </div>
  );
}