"use client";

import {
  ArchiveRestore,
  DatabaseBackup,
  FileArchive,
  Globe,
  KeyRound,
  Power,
  RotateCw,
  Server,
  ShieldCheck,
  Wifi,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useRef, useState } from "react";
import type { ChangeEvent } from "react";

import type { ManagementJob } from "@/lib/router-management";
import { useManagementJob } from "@/hooks/use-management-job";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { Widget } from "@/components/dashboard/widget";

type ActionDef = {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  group: "system" | "network";
};

const ACTIONS: ActionDef[] = [
  { id: "reboot", label: "Reboot", description: "Restart the whole router", icon: RotateCw, group: "system" },
  { id: "shutdown", label: "Shutdown", description: "Power the router down", icon: Power, group: "system" },
  { id: "restart-network", label: "Restart Network", description: "Restart all network interfaces", icon: Server, group: "system" },
  { id: "restart-wifi", label: "Restart WiFi", description: "Restart wireless radios", icon: Wifi, group: "system" },
  { id: "restart-firewall", label: "Restart Firewall", description: "Reload firewall rules", icon: ShieldCheck, group: "system" },
  { id: "restart-dnsmasq", label: "Restart DNSMasq", description: "Restart the DNSMasq service", icon: Globe, group: "system" },
  { id: "restart-dropbear", label: "Restart Dropbear", description: "Restart the SSH server", icon: KeyRound, group: "system" },
];

type Notice = { tone: "success" | "danger"; message: string };

/** Central place for management status messages (big, JSON-safe). */
function describeResult(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

/**
 * Router management: live reboot/shutdown/restart actions (each requiring
 * confirmation, with progress + result), sysupgrade backup/restore, and a
 * downloadable diagnostic bundle. Nothing is a placeholder — every control
 * reaches the backend over SSH and reports its outcome.
 */
export function ManagementActionsPanel() {
  const runner = useManagementJob();
  const [pendingAction, setPendingAction] = useState<ActionDef | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [pendingRestore, setPendingRestore] = useState<ManagementJob | null>(null);
  const fileInput = useRef<HTMLInputElement | null>(null);

  const dataAction = (job: ManagementJob | null) =>
    job !== null && (job.kind === "backup" || job.kind === "bundle") && job.status === "succeeded";

  const runActionFlow = async (action: ActionDef) => {
    setPendingAction(null);
    setNotice(null);
    try {
      const job = await runner.runAction(action.id);
      setNotice({ tone: job.status === "succeeded" ? "success" : "danger", message: describeResult(job) });
    } catch (e) {
      setNotice({ tone: "danger", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const createBackup = async () => {
    setNotice(null);
    try {
      await runner.createBackup();
    } catch (e) {
      setNotice({ tone: "danger", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const createBundle = async () => {
    setNotice(null);
    try {
      await runner.createBundle();
    } catch (e) {
      setNotice({ tone: "danger", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const onFileSelected = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) {
      return;
    }
    setNotice(null);
    setPendingRestore(null);
    try {
      const job = await runner.stageRestore(file);
      setPendingRestore(job);
    } catch (e) {
      setNotice({ tone: "danger", message: e instanceof Error ? e.message : String(e) });
    }
  };

  const confirmRestore = async () => {
    const job = pendingRestore;
    if (!job) {
      return;
    }
    setNotice(null);
    try {
      const finished = await runner.confirmRestore(job.id);
      setPendingRestore(null);
      if (fileInput.current) {
        fileInput.current.value = "";
      }
      setNotice({ tone: finished.status === "succeeded" ? "success" : "danger", message: describeResult(finished) });
    } catch (e) {
      setNotice({ tone: "danger", message: e instanceof Error ? e.message : String(e) });
    }
  };

  return (
    <Widget
      title="Management Actions"
      icon={DatabaseBackup}
      subtitle="Reboot, restart, backup and restore directly over SSH"
    >
      <div className="space-y-5">
        {runner.busy ? (
          <div className="space-y-1 rounded-md border bg-muted/40 px-3 py-2">
            <p className="text-sm font-medium">
              {runner.job?.status === "running" ? "Executing…" : "Working…"}
            </p>
            <p className="text-xs text-muted-foreground">{runner.job?.message ?? "Contacting the router…"}</p>
          </div>
        ) : null}

        {notice ? (
          <p
            className={
              notice.tone === "success"
                ? "rounded-md border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-700 dark:text-emerald-400"
                : "rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive"
            }
          >
            {notice.message}
          </p>
        ) : null}

        {/* System actions */}
        <section className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-semibold">System &amp; Network</h3>
            <span className="text-xs text-muted-foreground">Confirmation required</span>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {ACTIONS.map((action) => {
              const Icon = action.icon;
              return (
                <div key={action.id} className="flex items-center gap-3 rounded-md border p-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                    <Icon className="size-4 text-muted-foreground" aria-hidden />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium">{action.label}</p>
                    <p className="text-xs text-muted-foreground">{action.description}</p>
                  </div>
                  <Button
                    variant={action.id === "shutdown" ? "destructive" : "outline"}
                    size="sm"
                    disabled={runner.busy}
                    onClick={() => setPendingAction(action)}
                  >
                    Run
                  </Button>
                </div>
              );
            })}
          </div>
        </section>

        {/* Data: backup / bundle / restore */}
        <section className="space-y-2">
          <div className="flex items-baseline justify-between">
            <h3 className="text-sm font-semibold">Configuration &amp; Diagnostics</h3>
            <span className="text-xs text-muted-foreground">Backup · Bundle · Restore</span>
          </div>
          <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
            <div className="flex flex-col gap-3 rounded-md border p-3">
              <div className="flex items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                  <DatabaseBackup className="size-4 text-muted-foreground" aria-hidden />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">Backup</p>
                  <p className="text-xs text-muted-foreground">sysupgrade -b archive</p>
                </div>
              </div>
              {dataAction(runner.job) && runner.job?.kind === "backup" ? (
                <Button size="sm" onClick={() => runner.downloadArtifact(runner.job!)}>
                  Download backup
                </Button>
              ) : (
                <Button size="sm" variant="outline" disabled={runner.busy} onClick={createBackup}>
                  Create backup
                </Button>
              )}
            </div>

            <div className="flex flex-col gap-3 rounded-md border p-3">
              <div className="flex items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                  <FileArchive className="size-4 text-muted-foreground" aria-hidden />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">Diagnostic Bundle</p>
                  <p className="text-xs text-muted-foreground">logs, dmesg, config, packages…</p>
                </div>
              </div>
              {dataAction(runner.job) && runner.job?.kind === "bundle" ? (
                <Button size="sm" onClick={() => runner.downloadArtifact(runner.job!)}>
                  Download bundle
                </Button>
              ) : (
                <Button size="sm" variant="outline" disabled={runner.busy} onClick={createBundle}>
                  Generate bundle
                </Button>
              )}
            </div>

            <div className="flex flex-col gap-3 rounded-md border p-3">
              <div className="flex items-center gap-3">
                <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                  <ArchiveRestore className="size-4 text-muted-foreground" aria-hidden />
                </span>
                <div className="min-w-0">
                  <p className="text-sm font-medium">Restore</p>
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
              <Button size="sm" variant="outline" disabled={runner.busy} onClick={() => fileInput.current?.click()}>
                Choose &amp; stage backup
              </Button>
            </div>
          </div>

          {pendingRestore ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2">
              <div className="min-w-0 space-y-0.5">
                <p className="text-sm font-medium">Backup staged for restore</p>
                <p className="text-xs text-muted-foreground">
                  {(pendingRestore.result as { staged_filename?: string } | null)?.staged_filename ??
                    "validate the file and confirm to apply."}{" "}
                  The router will reboot after restore.
                </p>
              </div>
              <div className="flex items-center gap-2">
                <Button size="sm" variant="outline" disabled={runner.busy} onClick={() => setPendingRestore(null)}>
                  Discard
                </Button>
                <Button size="sm" variant="destructive" disabled={runner.busy} onClick={confirmRestore}>
                  Confirm restore
                </Button>
              </div>
            </div>
          ) : null}
        </section>
      </div>

      <ConfirmDialog
        open={pendingAction !== null}
        title={`${pendingAction?.label ?? ""} this router?`}
        description={`${pendingAction?.label ?? "This operation"} is disruptive and will be sent to the router immediately after you confirm.`}
        confirmLabel={pendingAction?.label ?? "Confirm"}
        busy={runner.busy}
        error={runner.error}
        onConfirm={() => pendingAction && runActionFlow(pendingAction)}
        onCancel={() => setPendingAction(null)}
      />
    </Widget>
  );
}