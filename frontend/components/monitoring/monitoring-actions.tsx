"use client";

import { Activity, RefreshCw } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { useState } from "react";

type Props = {
  busy?: boolean;
  notice: { tone: "success" | "danger"; message: string } | null;
  onRefresh: () => void;
  onRestart: () => void;
  onDismissNotice: () => void;
};

export function MonitoringActions({
  busy = false,
  notice,
  onRefresh,
  onRestart,
  onDismissNotice,
}: Props) {
  const [confirmRestart, setConfirmRestart] = useState(false);

  return (
    <Card>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Actions</h3>
          <p className="text-xs text-muted-foreground">
            Restart the router&apos;s monitoring daemon, or refresh all live data.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={onRefresh} disabled={busy}>
            <RefreshCw className={`size-4 ${busy ? "animate-spin" : ""}`} aria-hidden />
            Refresh data
          </Button>
          <Button variant="outline" onClick={() => setConfirmRestart(true)} disabled={busy}>
            <Activity className="size-4" aria-hidden />
            Restart monitoring
          </Button>
        </div>

        {notice ? (
          <button
            type="button"
            onClick={onDismissNotice}
            className={`flex w-full items-center justify-between gap-2 rounded-md border px-3 py-2 text-left text-sm ${
              notice.tone === "success"
                ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400"
                : "border-destructive/40 bg-destructive/10 text-destructive"
            }`}
          >
            <span>{notice.message}</span>
            <span className="shrink-0 text-xs opacity-70">Dismiss</span>
          </button>
        ) : null}
      </CardContent>

      <ConfirmDialog
        open={confirmRestart}
        title="Restart monitoring service?"
        description="The router's monitoring daemon (netdata, collectd, telegraf…) will be restarted. Live data may pause briefly."
        confirmLabel="Restart service"
        busy={busy}
        onConfirm={() => {
          setConfirmRestart(false);
          onRestart();
        }}
        onCancel={() => setConfirmRestart(false)}
      />
    </Card>
  );
}