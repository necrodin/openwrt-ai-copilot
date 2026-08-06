"use client";

import { RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";

type Props = {
  busy?: boolean;
  onReload: () => void;
  onRestart: () => void;
};

type PendingAction = "reload" | "restart" | null;

export function VpnActions({ busy = false, onReload, onRestart }: Props) {
  const [pending, setPending] = useState<PendingAction>(null);

  const run = (action: PendingAction) => {
    setPending(null);
    if (action === "reload") {
      onReload();
    } else if (action === "restart") {
      onRestart();
    }
  };

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RefreshCw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Reload VPN</p>
            <p className="text-xs text-muted-foreground">
              Re-apply the OpenVPN configuration without dropping established
              tunnels.
            </p>
          </div>
        </div>
        <Button variant="outline" disabled={busy} onClick={() => setPending("reload")}>
          {busy ? "Working…" : "Reload"}
        </Button>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RotateCcw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Restart VPN</p>
            <p className="text-xs text-muted-foreground">
              Fully restart the OpenVPN service — tunnels will briefly drop.
            </p>
          </div>
        </div>
        <Button variant="destructive" disabled={busy} onClick={() => setPending("restart")}>
          {busy ? "Working…" : "Restart"}
        </Button>
      </div>

      <ConfirmDialog
        open={pending === "reload"}
        title="Reload VPN?"
        description="The OpenVPN service will re-apply its configuration. Established tunnels are usually kept."
        confirmLabel="Reload"
        tone="default"
        busy={busy}
        onConfirm={() => run("reload")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "restart"}
        title="Restart VPN?"
        description="All OpenVPN instances will be restarted. Connected tunnels will disconnect briefly and reconnect."
        confirmLabel="Restart"
        busy={busy}
        onConfirm={() => run("restart")}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}