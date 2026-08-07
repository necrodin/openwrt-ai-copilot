"use client";

import { RefreshCw, RotateCcw } from "lucide-react";
import { useMemo, useState } from "react";

import type { NetworkInterface } from "@/lib/dashboard";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { cn } from "@/lib/utils";

type Props = {
  interfaces: NetworkInterface[];
  busy?: boolean;
  onRestartInterface: (section: string) => void;
  onRenew: (section: string) => void;
  onRelease: (section: string) => void;
  onReload: () => void;
  onRestart: () => void;
};

type PendingAction =
  | "restart-interface"
  | "renew"
  | "release"
  | "reload"
  | "restart"
  | null;

const DHCP_PROTOS = new Set(["dhcp", "dhcpv6", "pppoe", "ppp"]);

export function NetworkActions({
  interfaces,
  busy = false,
  onRestartInterface,
  onRenew,
  onRelease,
  onReload,
  onRestart,
}: Props) {
  const [pending, setPending] = useState<PendingAction>(null);
  const [selected, setSelected] = useState<string>("");

  const leaseTargets = useMemo(
    () =>
      interfaces.filter(
        (iface) => iface.proto !== null && DHCP_PROTOS.has(iface.proto),
      ),
    [interfaces],
  );

  const currentTarget = selected || leaseTargets[0]?.name || interfaces[0]?.name || "";

  const run = (action: PendingAction) => {
    setPending(null);
    if (action === "restart-interface") {
      onRestartInterface(currentTarget);
    } else if (action === "renew") {
      onRenew(currentTarget);
    } else if (action === "release") {
      onRelease(currentTarget);
    } else if (action === "reload") {
      onReload();
    } else if (action === "restart") {
      onRestart();
    }
  };

  const selectClasses =
    "h-9 w-full rounded-md border bg-background px-3 text-sm text-foreground shadow-xs";

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-3">
      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RefreshCw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Restart interface</p>
            <p className="text-xs text-muted-foreground">
              Bring an interface down and back up.
            </p>
          </div>
        </div>
        <div className="flex w-full items-center gap-2 md:w-auto">
          <select
            aria-label="Interface to restart"
            className={cn(selectClasses, "md:w-40")}
            value={currentTarget}
            onChange={(event) => setSelected(event.target.value)}
          >
            {interfaces.map((iface) => (
              <option key={iface.name} value={iface.name}>
                {iface.name}
              </option>
            ))}
          </select>
          <Button
            variant="outline"
            disabled={busy || !currentTarget}
            onClick={() => setPending("restart-interface")}
          >
            {busy ? "Working…" : "Restart"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RefreshCw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Renew DHCP lease</p>
            <p className="text-xs text-muted-foreground">
              Request a fresh lease on the selected interface.
            </p>
          </div>
        </div>
        <div className="flex w-full items-center gap-2 md:w-auto">
          <select
            aria-label="Interface to renew"
            className={cn(selectClasses, "md:w-40")}
            value={currentTarget}
            onChange={(event) => setSelected(event.target.value)}
          >
            {leaseTargets.length > 0 ? (
              leaseTargets.map((iface) => (
                <option key={iface.name} value={iface.name}>
                  {iface.name}
                </option>
              ))
            ) : (
              <option value="">No DHCP interface</option>
            )}
          </select>
          <Button
            variant="outline"
            disabled={busy || leaseTargets.length === 0}
            onClick={() => setPending("renew")}
          >
            {busy ? "Working…" : "Renew"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RefreshCw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Release DHCP lease</p>
            <p className="text-xs text-muted-foreground">
              Drop the current lease and take the interface down.
            </p>
          </div>
        </div>
        <div className="flex w-full items-center gap-2 md:w-auto">
          <select
            aria-label="Interface to release"
            className={cn(selectClasses, "md:w-40")}
            value={currentTarget}
            onChange={(event) => setSelected(event.target.value)}
          >
            {leaseTargets.length > 0 ? (
              leaseTargets.map((iface) => (
                <option key={iface.name} value={iface.name}>
                  {iface.name}
                </option>
              ))
            ) : (
              <option value="">No DHCP interface</option>
            )}
          </select>
          <Button
            variant="outline"
            disabled={busy || leaseTargets.length === 0}
            onClick={() => setPending("release")}
          >
            {busy ? "Working…" : "Release"}
          </Button>
        </div>
      </div>

      <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border p-4">
        <div className="flex items-center gap-3">
          <span className="flex size-10 shrink-0 items-center justify-center rounded-md border bg-muted">
            <RefreshCw className="size-5 text-muted-foreground" aria-hidden />
          </span>
          <div className="min-w-0">
            <p className="text-sm font-medium">Reload network</p>
            <p className="text-xs text-muted-foreground">
              Re-apply network configuration without dropping interfaces.
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
            <p className="text-sm font-medium">Restart network</p>
            <p className="text-xs text-muted-foreground">
              Fully restart networking — all interfaces will briefly drop.
            </p>
          </div>
        </div>
        <Button variant="destructive" disabled={busy} onClick={() => setPending("restart")}>
          {busy ? "Working…" : "Restart"}
        </Button>
      </div>

      <ConfirmDialog
        open={pending === "restart-interface"}
        title={`Restart ${currentTarget}?`}
        description={`The ${currentTarget} interface will be brought down and back up. Traffic on it will briefly drop.`}
        confirmLabel="Restart"
        busy={busy}
        onConfirm={() => run("restart-interface")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "renew"}
        title={`Renew lease on ${currentTarget}?`}
        description={`The DHCP client on ${currentTarget} will request a new lease. The interface may briefly drop.`}
        confirmLabel="Renew"
        tone="default"
        busy={busy}
        onConfirm={() => run("renew")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "release"}
        title={`Release lease on ${currentTarget}?`}
        description={`The DHCP client on ${currentTarget} will release its lease and the interface will be taken down.`}
        confirmLabel="Release"
        busy={busy}
        onConfirm={() => run("release")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "reload"}
        title="Reload network?"
        description="The network configuration will be re-applied. Established interfaces are usually kept."
        confirmLabel="Reload"
        tone="default"
        busy={busy}
        onConfirm={() => run("reload")}
        onCancel={() => setPending(null)}
      />

      <ConfirmDialog
        open={pending === "restart"}
        title="Restart network?"
        description="All network interfaces will be restarted. Connected devices will briefly lose connectivity."
        confirmLabel="Restart"
        busy={busy}
        onConfirm={() => run("restart")}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}