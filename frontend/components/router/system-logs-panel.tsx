"use client";

import { Download, Eraser, FileText, RefreshCw, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";

import { useSystemLogs } from "@/hooks/use-system-logs";
import type { ManagementLogEntry } from "@/lib/router-management";
import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { EmptyState, Widget, WidgetError } from "@/components/dashboard/widget";

type Level = "all" | "info" | "warning" | "error";

const MAX_BUFFER = 2000;

const ERROR_PRIORITIES = new Set(["err", "error", "crit", "alert", "emerg", "emergency", "panic", "fatal"]);
const WARN_PRIORITIES = new Set(["warning", "warn"]);

function levelOf(entry: ManagementLogEntry): Exclude<Level, "all"> {
  const priority = (entry.priority ?? "").toLowerCase();
  if (ERROR_PRIORITIES.has(priority)) {
    return "error";
  }
  if (WARN_PRIORITIES.has(priority)) {
    return "warning";
  }
  const message = (entry.message ?? "").toLowerCase();
  if (message.includes("fatal") || message.includes(" error ")) {
    return "error";
  }
  if (message.includes("warn")) {
    return "warning";
  }
  return "info";
}

function entryKey(entry: ManagementLogEntry): string {
  return `${entry.timestamp ?? ""}|${entry.facility ?? ""}|${entry.priority ?? ""}|${entry.message}`;
}

const levelOptions: { id: Level; label: string }[] = [
  { id: "all", label: "All" },
  { id: "info", label: "Info" },
  { id: "warning", label: "Warning" },
  { id: "error", label: "Error" },
];

const levelText: Record<Exclude<Level, "all">, string> = {
  info: "text-muted-foreground",
  warning: "text-amber-600 dark:text-amber-400",
  error: "text-red-600 dark:text-red-400",
};

const levelChip: Record<Exclude<Level, "all">, string> = {
  info: "bg-muted text-muted-foreground",
  warning: "bg-amber-500/15 text-amber-700 dark:text-amber-400",
  error: "bg-red-500/15 text-red-700 dark:text-red-400",
};

/**
 * Live system log viewer (real ``logread`` collection). Polls the feed,
 * streams new entries into a capped in-memory buffer, and provides search,
 * a severity filter, download of the current view, and a clear-screen action.
 */
export function SystemLogsPanel() {
  const { logs, loading, error, refetch, clearScreen } = useSysLogStream();
  const [level, setLevel] = useState<Level>("all");
  const [query, setQuery] = useState("");

  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    return logs.filter((entry) => {
      if (level !== "all" && levelOf(entry) !== level) {
        return false;
      }
      if (needle !== "" && !(entry.message ?? "").toLowerCase().includes(needle)) {
        return false;
      }
      return true;
    });
  }, [logs, level, query]);

  const counts = useMemo(
    () => ({
      all: logs.length,
      info: logs.filter((entry) => levelOf(entry) === "info").length,
      warning: logs.filter((entry) => levelOf(entry) === "warning").length,
      error: logs.filter((entry) => levelOf(entry) === "error").length,
    }),
    [logs],
  );

  const downloadVisible = () => {
    const body = visible
      .map((entry) => `[${entry.timestamp ?? "—"}] [${levelOf(entry).toUpperCase()}] ${entry.message}`)
      .join("\n");
    const url = URL.createObjectURL(new Blob([body], { type: "text/plain;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = "router-system-log.txt";
    anchor.click();
    URL.revokeObjectURL(url);
  };

  const body = (() => {
    if (loading && logs.length === 0) {
      return <Skeleton className="h-40 w-full" />;
    }
    if (!loading && logs.length === 0 && error !== null) {
      return <WidgetError message={error} />;
    }
    if (logs.length === 0) {
      return <EmptyState message="No system log entries were reported by the router." />;
    }
    return (
      <div className="space-y-3">
        <div className="flex flex-wrap items-center gap-2">
          <div className="relative min-w-40 flex-1">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
              aria-hidden
            />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search logs…"
              className="pl-9"
              aria-label="Search logs"
            />
          </div>
          <div
            className="flex items-center gap-1 rounded-md border bg-muted/40 p-0.5"
            role="group"
            aria-label="Filter by level"
          >
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
          <Button variant="outline" size="sm" onClick={downloadVisible} disabled={visible.length === 0}>
            <Download className="size-4" aria-hidden />
            Download
          </Button>
          <Button variant="outline" size="sm" onClick={clearScreen}>
            <Eraser className="size-4" aria-hidden />
            Clear
          </Button>
          <Button variant="outline" size="sm" onClick={() => refetch()}>
            <RefreshCw className="size-4" aria-hidden />
            Refresh
          </Button>
        </div>

        <div className="max-h-96 space-y-1 overflow-y-auto rounded-md border bg-muted/20 p-3 font-mono text-xs">
          {visible.length === 0 ? (
            <p className="text-muted-foreground">No log entries match the current filter.</p>
          ) : (
            visible.map((entry, index) => (
              <div key={index} className="flex gap-2">
                <span className="shrink-0 text-muted-foreground/60">{entry.timestamp ?? ""}</span>
                <span className="flex gap-1.5">
                  <span
                    className={cn(
                      "shrink-0 rounded px-1 py-0.5 text-[10px] font-semibold uppercase",
                      levelChip[levelOf(entry)],
                    )}
                  >
                    {levelOf(entry)}
                  </span>
                  <span className={cn("break-words", levelText[levelOf(entry)])}>
                    {entry.ident ? `[${entry.ident}] ` : ""}
                    {entry.message}
                  </span>
                </span>
              </div>
            ))
          )}
        </div>
        <p className="text-xs text-muted-foreground">
          Buffered {logs.length} of the most recent entries (capped at {MAX_BUFFER}).
        </p>
      </div>
    );
  })();

  return (
    <Widget
      title="System Logs"
      icon={FileText}
      subtitle={logs.length > 0 ? `${logs.length} buffered entries` : "No log feed"}
      loading={loading}
      error={error}
    >
      {body}
    </Widget>
  );
}

/** Returns the streaming log buffer (deduped, capped) plus controls. */
function useSysLogStream() {
  const { data, loading, error, refetch } = useSystemLogs();
  const [buffer, setBuffer] = useState<ManagementLogEntry[]>([]);
  const seen = useRef(new Set<string>());

  useEffect(() => {
    const entries = data?.logs ?? [];
    const fresh = entries.filter((entry) => {
      const key = entryKey(entry);
      if (seen.current.has(key)) {
        return false;
      }
      seen.current.add(key);
      return true;
    });
    if (fresh.length === 0) {
      return;
    }
    setBuffer((current) => [...current, ...fresh].slice(-MAX_BUFFER));
  }, [data]);

  const clearScreen = () => {
    setBuffer([]);
    seen.current = new Set((data?.logs ?? []).map(entryKey));
  };

  return { logs: buffer, loading, error, refetch, clearScreen };
}