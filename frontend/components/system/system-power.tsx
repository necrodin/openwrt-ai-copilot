"use client";

import { useState } from "react";
import { Power, RefreshCw, RotateCcw } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";

type Props = {
  busy?: boolean;
  onReboot: () => void;
  onShutdown: () => void;
  onFactoryReset: () => void;
};

type PowerAction = {
  key: "reboot" | "shutdown" | "factory-reset";
  label: string;
  title: string;
  description: string;
  confirmLabel: string;
  icon: typeof RefreshCw;
  tone: "outline" | "destructive";
};

const POWER_ACTIONS: PowerAction[] = [
  {
    key: "reboot",
    label: "Reboot",
    title: "Reboot this router?",
    description: "The router will restart immediately after you confirm.",
    confirmLabel: "Reboot",
    icon: RefreshCw,
    tone: "outline",
  },
  {
    key: "shutdown",
    label: "Shutdown",
    title: "Shut down this router?",
    description: "The router will power off. You will need physical access to start it again.",
    confirmLabel: "Shutdown",
    icon: Power,
    tone: "destructive",
  },
  {
    key: "factory-reset",
    label: "Factory reset",
    title: "Factory reset this router?",
    description:
      "All persisted configuration in /etc/config will be erased and the router will reboot to factory defaults. This cannot be undone.",
    confirmLabel: "Factory reset",
    icon: RotateCcw,
    tone: "destructive",
  },
];

export function SystemPower({ busy = false, onReboot, onShutdown, onFactoryReset }: Props) {
  const [pending, setPending] = useState<PowerAction | null>(null);

  const run = (action: PowerAction | null) => {
    setPending(null);
    if (action?.key === "reboot") {
      onReboot();
    } else if (action?.key === "shutdown") {
      onShutdown();
    } else if (action?.key === "factory-reset") {
      onFactoryReset();
    }
  };

  return (
    <Card>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Power</h3>
          <p className="text-xs text-muted-foreground">
            Reboot, shutdown or reset this router. Each requires confirmation.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
          {POWER_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <Button
                key={action.key}
                variant={action.tone}
                disabled={busy}
                className="h-auto flex-col items-start justify-start gap-1 p-3"
                onClick={() => setPending(action)}
              >
                <span className="flex items-center gap-2 text-sm font-medium">
                  <Icon className="size-4" aria-hidden />
                  {action.label}
                </span>
                <span className="text-xs font-normal opacity-80">
                  {action.description}
                </span>
              </Button>
            );
          })}
        </div>
      </CardContent>

      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? ""}
        description={pending?.description ?? ""}
        confirmLabel={pending?.confirmLabel ?? "Confirm"}
        busy={busy}
        onConfirm={() => run(pending)}
        onCancel={() => setPending(null)}
      />
    </Card>
  );
}