"use client";

import { Play, Power, RefreshCw, RotateCcw } from "lucide-react";
import { useState } from "react";

import type { FirewallInfo } from "@/lib/router-management";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  firewall: FirewallInfo;
  busy?: boolean;
  onAction: (action: "restart" | "reload" | "enable" | "disable") => void;
};

export function FirewallActions({ firewall, busy = false, onAction }: Props) {
  const [pending, setPending] = useState<{
    action: "restart" | "reload" | "enable" | "disable";
    title: string;
    description: string;
    label: string;
  } | null>(null);

  const confirm = () => {
    if (pending) {
      onAction(pending.action);
      setPending(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            setPending({
              action: "reload",
              label: "Reload",
              title: "Reload firewall",
              description:
                "Apply the current configuration without dropping established connections.",
            })
          }
        >
          <RefreshCw className="size-4" aria-hidden />
          Reload
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            setPending({
              action: "restart",
              label: "Restart",
              title: "Restart firewall",
              description:
                "Restart the firewall from scratch. Established connections will be dropped.",
            })
          }
        >
          <RotateCcw className="size-4" aria-hidden />
          Restart
        </Button>
        <Button
          variant="outline"
          disabled={busy}
          onClick={() =>
            setPending({
              action: "enable",
              label: "Enable",
              title: "Enable firewall",
              description: "Turn the firewall back on and restart it.",
            })
          }
        >
          <Play className="size-4" aria-hidden />
          Enable
        </Button>
        <Button
          variant="outline"
          disabled={busy || !firewall.enabled}
          onClick={() =>
            setPending({
              action: "disable",
              label: "Disable",
              title: "Disable firewall",
              description:
                "Disable the firewall entirely. The router will no longer filter traffic.",
            })
          }
        >
          <Power className="size-4" aria-hidden />
          Disable
        </Button>
      </div>

      <div className="flex flex-wrap items-center gap-3 rounded-md border bg-muted/40 px-3 py-2 text-sm">
        <span className="text-muted-foreground">Firewall state</span>
        <StatusBadge
          label={firewall.running ? "running" : "stopped"}
          tone={firewall.running ? "success" : "danger"}
          dot
        />
        <StatusBadge
          label={firewall.enabled ? "enabled" : "disabled"}
          tone={firewall.enabled ? "success" : "danger"}
          dot
        />
      </div>

      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ""}
        description={pending?.description ?? ""}
        confirmLabel={pending?.label ?? "Confirm"}
        tone={pending?.action === "disable" ? "destructive" : "default"}
        busy={busy}
        onConfirm={confirm}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}