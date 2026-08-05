"use client";

import { Download, FileText, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { EmptyState, Widget } from "@/components/dashboard/widget";

export type LogEntry = {
  level: "info" | "warning" | "error";
  message: string;
  timestamp?: string | null;
};

type LogLevel = "all" | "info" | "warning" | "error";

type Props = {
  lines: LogEntry[];
  loading?: boolean;
  error?: string | null;
  /** Called when the user requests a refresh of the log feed. */
  onRefresh?: () => void;
};

const levelOptions: { id: LogLevel; label: string }[] = [
  { id: "all", label: "All" },
  { id: "info", label: "Info" },
  { id: "warning", label: "Warning" },
  { id: "error", label: "Error" },
];

const levelText: Record<LogEntry["level"], string> = {
  info: "text-muted-foreground",
  warning: "text-amber-600 dark:text-amber-400",
  error: "text-red-600 dark:text-red-400",
};

const levelChip: Record<LogEntry["level"], string> = {
  info: "bg-muted text-muted-foreground",
  warning: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  error: "bg-red-500/15 text-red-700 dark:text-red-400",
};

function download(lines: LogEntry[]) {
  const body = lines
    .map((entry) => `[${entry.timestamp ?? "—"}] [${entry.level.toUpperCase()}] ${entry.message}`)
    .join("\n");
  const url = URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "router-system-log.txt";
  anchor.click();
  URL.revokeObjectURL(url);
}

/**
 * Live system log viewer for the System Logs section. Provides level filtering,
 * free-text search and a download of the current view. The feed is only
 * populated when the backend collector serves `snapshot.logs`; until then the
 * viewer renders an explicit empty state with disabled controls.
 */
export function SystemLogsPanel({ lines, loading = false, error = null, onRefresh }: Props) {
  const [level, setLevel] = useState<LogLevel>("all");
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return lines.filter((entry) => {
      if (level !== "all" && entry.level !== level) {
        return false;
      }
      if (needle !== "" && !entry.message.toLowerCase().includes(needle)) {
        return false;
      }
      return true;
    });
  }, [lines, level, query]);

  const counts = useMemo(
    () => ({
      all: lines.length,
      info: lines.filter((entry) => entry.level === "info").length,
      warning: lines.filter((entry) => entry.level === "warning").length,
      error: lines.filter((entry) => entry.level === "error").length,
    }),
    [lines],
  );

  const hasLogs = lines.length > 0;

  return (
    <Widget
      title="System Logs"
      icon={FileText}
      subtitle={hasLogs ? `${lines.length} entries` : "No log feed"}
      loading={loading}
      error={error}
    >
      {!hasLogs ? (
        <EmptyState message="No system log feed is exposed by the current collector. Live logging, filtering and download will light up when the log endpoint ships in a later sprint." />
      ) : (
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-40 flex-1">
              <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
              <Input
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                placeholder="Search logs…"
                className="pl-9"
                aria-label="Search logs"
              />
            </div>
            <div className="flex items-center gap-1 rounded-md border bg-muted/40 p-0.5" role="group" aria-label="Filter by level">
              {levelOptions.map((option) => (
                <button
                  key={option.id}
                  type="button"
                  onClick={() => setLevel(option.id)}
                  aria-pressed={level === option.id}
                  className={cn(
                    "rounded px-2.5 py-1 text-xs font-medium transition-colors",
                    level === option.id
                      ? "bg-background text-foreground shadow-sm"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {option.label}
                  <span className="ml-1 tabular-nums text-[10px]">{counts[option.id]}</span>
                </button>
              ))}
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => download(visible)}
              disabled={visible.length === 0}
              title={visible.length === 0 ? "Nothing to download" : "Download visible logs"}
            >
              <Download className="size-4" aria-hidden />
              Download
            </Button>
            <Button variant="outline" size="sm" onClick={onRefresh}>
              <RefreshCw className="size-4" aria-hidden />
              Refresh
            </Button>
          </div>

          <div className="max-h-80 space-y-1 overflow-y-auto rounded-md border bg-muted/20 p-3 font-mono text-xs">
            {visible.length === 0 ? (
              <p className="text-muted-foreground">No log entries match the current filter.</p>
            ) : (
              visible.map((entry, index) => (
                <div key={index} className="flex gap-2">
                  <span className="shrink-0 text-muted-foreground/60">
                    {entry.timestamp ?? ""}
                  </span>
                  <span className="flex gap-1.5">
                    <span
                      className={cn(
                        "shrink-0 rounded px-1 py-0.5 text-[10px] font-semibold uppercase",
                        levelChip[entry.level],
                      )}
                    >
                      {entry.level}
                    </span>
                    <span className={cn("break-words", levelText[entry.level])}>
                      {entry.message}
                    </span>
                  </span>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </Widget>
  );
}