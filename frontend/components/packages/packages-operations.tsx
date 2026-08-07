"use client";

import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import type { ManagementJob } from "@/lib/router-management";
import { Widget } from "@/components/dashboard/widget";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  job: ManagementJob | null;
  busy: boolean;
};

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

/**
 * Live package operations log: shows the most recent management job triggered
 * from this page (install / remove / upgrade / reinstall / update feeds) with
 * its progress, success, or failure state.
 */
export function PackagesOperations({ job, busy }: Props) {
  const running = busy && job !== null && (job.status === "queued" || job.status === "running");

  return (
    <Widget
      title="Operations"
      icon={running ? Loader2 : CheckCircle2}
      subtitle="Recent package management jobs and their outcome."
    >
      {job === null ? (
        <p className="text-sm text-muted-foreground">
          No package operations have run yet. Actions from this page appear here with their status.
        </p>
      ) : (
        <div className="flex items-start gap-3 rounded-md border px-3 py-3 text-sm">
          {running ? (
            <Loader2 className="mt-0.5 size-4 animate-spin text-primary" aria-hidden />
          ) : job.status === "succeeded" ? (
            <CheckCircle2 className="mt-0.5 size-4 text-emerald-500" aria-hidden />
          ) : (
            <XCircle className="mt-0.5 size-4 text-destructive" aria-hidden />
          )}
          <div className="min-w-0 flex-1 space-y-1">
            <div className="flex items-center gap-2">
              <p className="font-medium">
                {job.status === "running" || job.status === "queued"
                  ? "Package operation in progress"
                  : job.status === "succeeded"
                    ? "Package operation succeeded"
                    : "Package operation failed"}
              </p>
              <StatusBadge
                tone={
                  running
                    ? "info"
                    : job.status === "succeeded"
                      ? "success"
                      : "danger"
                }
                label={job.status}
              />
            </div>
            <p className="text-muted-foreground">{describe(job)}</p>
            {job.error ? <p className="text-destructive">{job.error}</p> : null}
          </div>
        </div>
      )}
    </Widget>
  );
}