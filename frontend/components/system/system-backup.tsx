"use client";

import { useRef, useState, type ChangeEvent } from "react";
import { DatabaseBackup, ArchiveRestore, Download } from "lucide-react";

import type { ManagementJob } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type Props = {
  busy?: boolean;
  job: ManagementJob | null;
  onCreate: () => Promise<ManagementJob>;
  onStage: (file: File) => Promise<ManagementJob>;
  onConfirm: (jobId: string) => Promise<ManagementJob>;
  onDownload: (job: ManagementJob) => Promise<void>;
};

export function SystemBackup({
  busy = false,
  job,
  onCreate,
  onStage,
  onConfirm,
  onDownload,
}: Props) {
  const [pendingRestore, setPendingRestore] = useState<ManagementJob | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const backupReady =
    job !== null && job.kind === "backup" && job.status === "succeeded";

  const onFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    setPendingRestore(null);
    try {
      setPendingRestore(await onStage(file));
    } catch {
      setPendingRestore(null);
    }
  };

  const confirmRestore = async () => {
    if (!pendingRestore) {
      return;
    }
    const jobId = pendingRestore.id;
    setPendingRestore(null);
    try {
      await onConfirm(jobId);
      if (fileInput.current) {
        fileInput.current.value = "";
      }
    } catch {
      setPendingRestore(null);
    }
  };

  return (
    <Card>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">Backup &amp; Restore</h3>
          <p className="text-xs text-muted-foreground">
            Download a sysupgrade backup, or upload one to restore — the router
            reboots after a restore.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          <div className="flex flex-col gap-3 rounded-md border p-3">
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                <DatabaseBackup className="size-4 text-muted-foreground" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium">Backup configuration</p>
                <p className="text-xs text-muted-foreground">sysupgrade -b archive</p>
              </div>
            </div>
            {backupReady ? (
              <Button size="sm" onClick={() => void onDownload(job!)} disabled={busy}>
                <Download className="size-4" aria-hidden />
                Download backup
              </Button>
            ) : (
              <Button size="sm" variant="outline" disabled={busy} onClick={() => void onCreate()}>
                Create backup
              </Button>
            )}
          </div>

          <div className="flex flex-col gap-3 rounded-md border p-3">
            <div className="flex items-center gap-3">
              <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                <ArchiveRestore className="size-4 text-muted-foreground" aria-hidden />
              </span>
              <div className="min-w-0">
                <p className="text-sm font-medium">Restore configuration</p>
                <p className="text-xs text-muted-foreground">Upload a sysupgrade backup</p>
              </div>
            </div>
            <input
              ref={fileInput}
              type="file"
              accept=".tar.gz,.tgz,.gz"
              className="hidden"
              onChange={onFileSelected}
            />
            <Button
              size="sm"
              variant="outline"
              disabled={busy}
              onClick={() => fileInput.current?.click()}
            >
              Choose &amp; stage backup
            </Button>
          </div>
        </div>

        {pendingRestore ? (
          <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">
            <div className="min-w-0 space-y-0.5">
              <p className="text-sm font-medium">Backup staged for restore</p>
              <p className="text-xs text-muted-foreground">
                The file was validated. Confirm to restore — the router will reboot.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="outline" disabled={busy} onClick={() => setPendingRestore(null)}>
                Discard
              </Button>
              <Button size="sm" variant="destructive" disabled={busy} onClick={() => void confirmRestore()}>
                Confirm restore
              </Button>
            </div>
          </div>
        ) : null}
      </CardContent>
    </Card>
  );
}