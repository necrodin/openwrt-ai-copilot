"use client";

import { Power, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";

type Props = {
  enabled: boolean;
  busy?: boolean;
  onSetEnabled: (enabled: boolean) => void;
  onReload: () => void;
  onRestart: () => void;
};

type PendingAction = "disable" | "reload" | "restart" | null;

export function DhcpActions({ enabled, busy = false, onSetEnabled, onReload, onRestart }: Props) {
  const [pending, setPending] = useState<PendingAction>(null);

  const run = (action: PendingAction) => {
    setPending(null);
    if (action === "disable") {
      onSetEnabled(false);
    } else if (action === "reload") {
      onReload();
    } else if (action === "restart") {
      onRestart();
    }
  };

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <Power className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">DHCP Server</p>
            <p className="text-xs text-muted-foreground">
              {enabled ? "Serving leases on this router." : "The server is currently stopped."}
            </p>
          </div>
        </div>
        {enabled ? (
          <Button variant="destructive" disabled={busy} onClick={() => setPending("disable")}>
            {busy ? "Working…" : "Disable"}
          </Button>
        ) : (
          <Button disabled={busy} onClick={() => onSetEnabled(true)}>
            {busy ? "Working…" : "Enable"}
          </Button>
        )}
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RefreshCw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Reload DHCP</p>
            <p className="text-xs text-muted-foreground">
              Re-apply the configuration without dropping leases.
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
            <p className="text-sm font-medium">Restart DHCP</p>
            <p className="text-xs text-muted-foreground">
              Restart dnsmasq — active leases will briefly drop.
            </p>
          </div>
        </div>
        <Button variant="outline" disabled={busy} onClick={() => setPending("restart")}>
          {busy ? "Working…" : "Restart"}
        </Button>
      </div>

      <ConfirmDialog
        open={pending === "disable"}
        title="Disable DHCP?"
        description="The dnsmasq DHCP server will stop assigning addresses. Devices currently using the range will keep their leases until they expire."
        confirmLabel="Disable"
        busy={busy}
        onConfirm={() => run("disable")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "reload"}
        title="Reload DHCP?"
        description="dnsmasq will re-apply its configuration. Existing leases are usually kept."
        confirmLabel="Reload"
        tone="default"
        busy={busy}
        onConfirm={() => run("reload")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "restart"}
        title="Restart DHCP?"
        description="dnsmasq will be restarted. Clients will briefly lose DHCP service and then re-request addresses."
        confirmLabel="Restart"
        busy={busy}
        onConfirm={() => run("restart")}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}