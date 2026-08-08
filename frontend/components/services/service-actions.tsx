"use client";

import { Ban, Play, PowerOff, RefreshCw, ToggleRight } from "lucide-react";
import { useState } from "react";

import type { RouterService, ServiceAction } from "@/lib/router-management";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { EmptyState } from "@/components/dashboard/widget";

type Props = {
  service: RouterService | null;
  busy?: boolean;
  onAction: (action: ServiceAction, name: string) => void;
};

type Pending = { action: ServiceAction; name: string } | null;

const ACTION_META: Record<
  ServiceAction,
  { label: string; tone: "default" | "destructive"; description: string }
> = {
  start: {
    label: "Start",
    tone: "default",
    description: "{service} will be started. It will run until it is stopped or the router reboots.",
  },
  stop: {
    label: "Stop",
    tone: "destructive",
    description: "{service} will be stopped. Anything relying on it will be interrupted.",
  },
  restart: {
    label: "Restart",
    tone: "default",
    description: "{service} will be stopped and started again — a brief interruption is expected.",
  },
  enable: {
    label: "Enable",
    tone: "default",
    description: "{service} will start automatically whenever the router boots.",
  },
  disable: {
    label: "Disable",
    tone: "destructive",
    description: "{service} will no longer start at boot. Stop it now or it keeps running until reboot.",
  },
};

function ActionButton({
  action,
  onClick,
  disabled,
  variant,
}: {
  action: ServiceAction;
  onClick: () => void;
  disabled: boolean;
  variant: "outline" | "destructive";
}) {
  const icons: Record<ServiceAction, typeof Play> = {
    start: Play,
    stop: PowerOff,
    restart: RefreshCw,
    enable: ToggleRight,
    disable: Ban,
  };
  const Icon = icons[action];
  const meta = ACTION_META[action];
  return (
    <Button variant={variant} disabled={disabled} onClick={onClick} className="gap-2">
      <Icon className="size-4" aria-hidden />
      {meta.label}
    </Button>
  );
}

/**
 * Service actions: start / stop / restart / enable / disable for the selected
 * service. Every action (destructive or not) is guarded by the shared
 * confirmation dialog before it touches the router.
 */
export function ServiceActions({ service, busy = false, onAction }: Props) {
  const [pending, setPending] = useState<Pending>(null);

  if (service === null) {
    return (
      <Card>
        <CardContent>
          <EmptyState message="Select a service to manage it." />
        </CardContent>
      </Card>
    );
  }

  const run = (action: ServiceAction) => {
    if (!pending) return;
    setPending(null);
    onAction(action, pending.name);
  };

  const meta = pending ? ACTION_META[pending.action] : null;

  return (
    <Card>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <h3 className="flex items-center gap-2 text-sm font-semibold">
            <RefreshCw className="size-4 text-muted-foreground" aria-hidden />
            Service actions
          </h3>
          <p className="text-xs text-muted-foreground">
            Controls for <span className="font-mono font-medium">{service.name}</span>.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          {!service.running ? (
            <ActionButton
              action="start"
              variant="outline"
              disabled={busy}
              onClick={() => setPending({ action: "start", name: service.name })}
            />
          ) : null}
          {service.running ? (
            <>
              <ActionButton
                action="stop"
                variant="destructive"
                disabled={busy}
                onClick={() => setPending({ action: "stop", name: service.name })}
              />
              <ActionButton
                action="restart"
                variant="outline"
                disabled={busy}
                onClick={() => setPending({ action: "restart", name: service.name })}
              />
            </>
          ) : null}
          {service.enabled !== true ? (
            <ActionButton
              action="enable"
              variant="outline"
              disabled={busy}
              onClick={() => setPending({ action: "enable", name: service.name })}
            />
          ) : (
            <ActionButton
              action="disable"
              variant="destructive"
              disabled={busy}
              onClick={() => setPending({ action: "disable", name: service.name })}
            />
          )}
        </div>

        <ConfirmDialog
          open={pending !== null}
          title={pending ? `${meta?.label ?? "Run"} ${pending.name}?` : ""}
          description={meta ? meta.description.replace("{service}", pending?.name ?? "") : ""}
          confirmLabel={meta?.label ?? "Confirm"}
          tone={meta?.tone ?? "default"}
          busy={busy}
          onConfirm={() => {
            if (pending) {
              run(pending.action);
            }
          }}
          onCancel={() => setPending(null)}
        />
      </CardContent>
    </Card>
  );
}