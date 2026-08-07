"use client";

import { RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { RouterProcess } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { formatBytes } from "@/lib/dashboard-utils";

type SortKey = "cpu" | "mem" | "pid";

type Props = {
  processes: RouterProcess[];
  loading?: boolean;
  error?: string | null;
  onRefresh: () => void;
  onKill: (pid: number) => Promise<boolean>;
};

export function MonitoringProcesses({
  processes,
  loading = false,
  error = null,
  onRefresh,
  onKill,
}: Props) {
  const [query, setQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("cpu");
  const [sortDesc, setSortDesc] = useState(true);
  const [pending, setPending] = useState<RouterProcess | null>(null);

  const rows = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const filtered = needle
      ? processes.filter(
          (proc) =>
            proc.name.toLowerCase().includes(needle) ||
            proc.command.toLowerCase().includes(needle) ||
            proc.user.toLowerCase().includes(needle) ||
            String(proc.pid).includes(needle),
        )
      : processes;

    const factor = sortDesc ? -1 : 1;
    return [...filtered].sort((a, b) => {
      const av = sortKey === "pid" ? a.pid : sortKey === "cpu" ? a.cpu : a.mem ?? -1;
      const bv = sortKey === "pid" ? b.pid : sortKey === "cpu" ? b.cpu : b.mem ?? -1;
      return (av - bv) * factor;
    });
  }, [processes, query, sortKey, sortDesc]);

  const toggleSort = (key: SortKey) => {
    if (key === sortKey) {
      setSortDesc((value) => !value);
    } else {
      setSortKey(key);
      setSortDesc(true);
    }
  };

  const SortButton = ({ label, column, className }: { label: string; column: SortKey; className?: string }) => (
    <button
      type="button"
      onClick={() => toggleSort(column)}
      className={`inline-flex w-full items-center gap-1 text-left text-xs font-medium uppercase tracking-wide text-muted-foreground hover:text-foreground ${className ?? ""}`}
      aria-label={`Sort by ${label}`}
    >
      {label}
      <span className="tabular-nums" aria-hidden>
        {sortKey === column ? (sortDesc ? "↓" : "↑") : ""}
      </span>
    </button>
  );

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <h3 className="text-sm font-semibold">Processes</h3>
            <p className="text-xs text-muted-foreground">
              {rows.length} of {processes.length} processes
              {error ? ` · ${error}` : ""}
            </p>
          </div>
          <div className="flex items-center gap-2">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <input
                type="search"
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search pid, name, user…"
                className="h-9 w-52 rounded-md border bg-background pl-8 pr-3 text-sm outline-none focus:ring-2 focus:ring-ring"
                aria-label="Filter processes"
              />
            </div>
            <Button variant="outline" size="sm" onClick={onRefresh} disabled={loading}>
              <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} aria-hidden />
              <span className="sr-only">Refresh processes</span>
            </Button>
          </div>
        </div>

        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[44rem] text-left text-sm">
            <thead className="bg-muted/50 text-xs uppercase tracking-wide text-muted-foreground">
              <tr>
                <th className="px-3 py-2">
                  <SortButton label="PID" column="pid" />
                </th>
                <th className="px-3 py-2">Name</th>
                <th className="px-3 py-2">User</th>
                <th className="px-3 py-2 text-right">
                  <SortButton label="CPU" column="cpu" className="justify-end" />
                </th>
                <th className="px-3 py-2 text-right">
                  <SortButton label="Memory" column="mem" className="justify-end" />
                </th>
                <th className="px-3 py-2 text-right">RSS</th>
                <th className="px-3 py-2 text-right">VSZ</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody className="divide-y">
              {rows.length === 0 ? (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center text-muted-foreground">
                    {query ? "No processes match your search." : "No process data available."}
                  </td>
                </tr>
              ) : (
                rows.slice(0, 200).map((proc) => (
                  <tr key={proc.pid} className="hover:bg-muted/40">
                    <td className="px-3 py-2 tabular-nums text-muted-foreground">{proc.pid}</td>
                    <td className="max-w-40 truncate px-3 py-2 font-medium" title={proc.name}>
                      {proc.name}
                    </td>
                    <td className="px-3 py-2 text-muted-foreground">{proc.user}</td>
                    <td className="px-3 py-2 text-right tabular-nums">{proc.cpu.toFixed(1)}%</td>
                    <td className="px-3 py-2 text-right tabular-nums">
                      {proc.mem != null ? `${proc.mem.toFixed(1)}%` : "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {formatBytes(proc.rss)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-muted-foreground">
                      {formatBytes(proc.vsz ?? 0)}
                    </td>
                    <td className="px-3 py-2 text-right">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={proc.pid === 1}
                        onClick={() => setPending(proc)}
                      >
                        Kill
                      </Button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </CardContent>

      <ConfirmDialog
        open={pending !== null}
        title={`Kill process ${pending?.pid ?? ""}?`}
        description={`"${pending?.name ?? ""}" (${pending?.command ?? ""}) will be terminated with SIGTERM.`}
        confirmLabel="Kill process"
        busy={false}
        onConfirm={() => {
          if (pending) {
            void onKill(pending.pid);
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </Card>
  );
}