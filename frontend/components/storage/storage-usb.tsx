"use client";

import { Usb } from "lucide-react";
import { useState } from "react";

import type { StorageAction, StorageInfo } from "@/lib/router-management";
import { formatBytes } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { StatusBadge } from "@/components/ui/status-badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  storage: StorageInfo | null;
  busy?: boolean;
  onAction: (action: StorageAction, target: string) => void;
};

type PendingAction = { action: StorageAction; device: string; target: string } | null;

/**
 * Removable USB storage. Lists each drive with capacity and mount state, and
 * runs mount / unmount / remount through the management job framework — every
 * mutation is guarded by an explicit confirmation dialog.
 */
export function StorageUsb({ storage, busy = false, onAction }: Props) {
  const devices = storage?.usb ?? [];
  const [pending, setPending] = useState<PendingAction>(null);

  const run = (action: StorageAction, device: string, target: string) => {
    setPending(null);
    onAction(action, target);
  };

  return (
    <Widget
      title="USB storage"
      icon={Usb}
      subtitle={
        storage
          ? `${devices.length} drive${devices.length === 1 ? "" : "s"} · ${devices.filter((device) => device.mounted).length} mounted`
          : "Storage inventory loading…"
      }
    >
      {devices.length === 0 ? (
        <EmptyState message="No removable USB storage was detected. Insert a drive and it will appear here." />
      ) : (
        <div className="space-y-3">
          {devices.map((device) => {
            const mounted = device.mounted;
            const target = mounted && device.mountpoint
              ? device.mountpoint
              : `/dev/${device.device}`;
            const model = [device.vendor, device.model].filter(Boolean).join(" ") || device.device;
            return (
              <div
                key={device.device}
                className="flex flex-wrap items-center justify-between gap-3 rounded-md border px-3 py-3"
              >
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="font-mono text-xs font-medium">{device.device}</p>
                    {mounted ? (
                      <StatusBadge label="Mounted" tone="success" />
                    ) : (
                      <StatusBadge label="Not mounted" tone="neutral" />
                    )}
                  </div>
                  <p className="truncate text-sm font-medium">{model}</p>
                  <p className="text-xs text-muted-foreground tabular-nums">
                    {formatBytes(device.capacity)}
                    {mounted && device.mountpoint
                      ? ` · mounted at ${device.mountpoint}`
                      : ""}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {mounted ? (
                    <>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          setPending({ action: "remount", device: device.device, target })
                        }
                      >
                        Remount
                      </Button>
                      <Button
                        variant="outline"
                        disabled={busy}
                        onClick={() =>
                          setPending({ action: "unmount", device: device.device, target })
                        }
                      >
                        Unmount
                      </Button>
                    </>
                  ) : (
                    <Button
                      variant="outline"
                      disabled={busy}
                      onClick={() =>
                        setPending({ action: "mount", device: device.device, target })
                      }
                    >
                      Mount
                    </Button>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <ConfirmDialog
        open={pending !== null}
        title={
          pending
            ? pending.action === "mount"
              ? `Mount ${pending.device}?`
              : pending.action === "unmount"
                ? `Unmount ${pending.device}?`
                : `Remount ${pending.device}?`
            : ""
        }
        description={
          pending
            ? pending.action === "unmount"
              ? `${pending.target} will be unmounted. Any open files on it will be interrupted.`
              : pending.action === "remount"
                ? `${pending.target} will be remounted, re-applying its mount options.`
                : `${pending.target} will be mounted for use on this router.`
            : ""
        }
        confirmLabel={
          pending
            ? pending.action === "unmount"
              ? "Unmount"
              : pending.action === "remount"
                ? "Remount"
                : "Mount"
            : "Confirm"
        }
        tone={pending?.action === "unmount" ? "destructive" : "default"}
        busy={busy}
        onConfirm={() => {
          if (pending) {
            run(pending.action, pending.device, pending.target);
          }
        }}
        onCancel={() => setPending(null)}
      />
    </Widget>
  );
}