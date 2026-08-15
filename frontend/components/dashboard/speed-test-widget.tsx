"use client";

import {
  Activity,
  Download,
  Loader2,
  RefreshCw,
  Timer,
  Upload,
  Zap,
} from "lucide-react";
import { useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  formatLatency,
  formatSpeed,
  formatSpeedTestTimestamp,
  latestSpeedTest,
  runSpeedTest,
  speedStageLabel,
  type SpeedTestResult,
  type SpeedTestStage,
} from "@/lib/speed-test";
import { cn } from "@/lib/utils";

const STAGES: SpeedTestStage[] = ["testing", "latency", "downloading", "uploading"];

type MetricProps = {
  icon: typeof Download;
  label: string;
  value: string;
  unit: string;
  accent: string;
};

function Metric({ icon: Icon, label, value, unit, accent }: MetricProps) {
  return (
    <div className="rounded-xl border border-white/10 bg-white/5 px-3 py-2.5 text-center backdrop-blur-sm">
      <Icon className="mx-auto mb-1 size-4 text-cyan-300/80" aria-hidden />
      <p className={cn("text-lg font-bold tabular-nums sm:text-xl", accent)}>{value}</p>
      <p className="mt-0.5 text-[11px] uppercase tracking-wide text-slate-400">
        {label} <span className="text-slate-500">{unit}</span>
      </p>
    </div>
  );
}

/**
 * Network Speed Test — a visually distinct diagnostic card for the top of the
 * Dashboard.
 *
 * Runs the backend's read-only internet speed test (latency/jitter/download/
 * upload) with proper TLS-verified transfers, shows clear running progress,
 * then the measured values and a "Last test" timestamp. The latest result is
 * re-read on mount so the card survives page navigations without re-running a
 * test. Sub-measurements that could not be performed render as "—" with a
 * limitations note instead of failing the whole card.
 */
export function SpeedTestWidget() {
  const [result, setResult] = useState<SpeedTestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState<SpeedTestStage>("testing");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    latestSpeedTest()
      .then((response) => {
        if (!cancelled) {
          setResult(response.result);
        }
      })
      .catch(() => {
        // Unreachable/unauthorized: the card simply shows "Never" until a test
        // is requested; the action surfaces the real error.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Cosmetic progress cycler — the backend runs the measurement as one call, so
  // the stages shown are a faithful sequence of what is being measured.
  useEffect(() => {
    if (!busy) {
      return;
    }
    const id = window.setInterval(() => {
      setStage((current) => STAGES[(STAGES.indexOf(current) + 1) % STAGES.length]);
    }, 1400);
    return () => window.clearInterval(id);
  }, [busy]);

  const start = async () => {
    if (busy) {
      return; // guard against duplicate concurrent tests
    }
    setBusy(true);
    setStage("testing");
    setError(null);
    try {
      const measured = await runSpeedTest();
      setResult(measured);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const value = busy ? "…" : "—";
  const download = busy ? value : formatSpeed(result?.download_mbps ?? null);
  const upload = busy ? value : formatSpeed(result?.upload_mbps ?? null);
  const ping = busy ? value : formatLatency(result?.ping_ms ?? null);
  const jitter = busy ? value : formatLatency(result?.jitter_ms ?? null);

  return (
    <div className="relative overflow-hidden rounded-xl border border-slate-800 bg-gradient-to-br from-slate-950 via-slate-900 to-slate-950 p-4 text-slate-100 shadow-lg lg:col-span-3">
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 top-0 h-1 bg-gradient-to-r from-cyan-500 via-emerald-400 to-sky-500"
      />
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="grid size-9 place-items-center rounded-lg bg-cyan-500/15 text-cyan-300">
            <Activity className="size-4" aria-hidden />
          </span>
          <div>
            <p className="text-sm font-semibold">Network Speed Test</p>
            <p className="text-xs text-slate-400">Internet throughput &amp; latency</p>
          </div>
        </div>
        <Button
          type="button"
          size="sm"
          onClick={() => void start()}
          disabled={busy}
          className="shrink-0"
        >
          {busy ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : (
            <RefreshCw className="size-4" aria-hidden />
          )}
          {busy ? "Testing…" : "Run Test"}
        </Button>
      </div>

      {error ? (
        <p className="mt-3 text-sm text-red-400" role="alert">
          {error}
        </p>
      ) : (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Metric icon={Download} label="Download" value={download} unit="Mbps" accent="text-emerald-300" />
            <Metric icon={Upload} label="Upload" value={upload} unit="Mbps" accent="text-sky-300" />
            <Metric icon={Timer} label="Ping" value={ping} unit="ms" accent="text-amber-300" />
            <Metric icon={Zap} label="Jitter" value={jitter} unit="ms" accent="text-fuchsia-300" />
          </div>

          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-xs text-slate-400">
              Last test: {busy ? "running…" : formatSpeedTestTimestamp(result?.timestamp)}
            </p>
            {busy ? <StatusBadge label={speedStageLabel(stage)} tone="info" /> : null}
          </div>

          {!busy && result !== null && result.limitations.length > 0 ? (
            <ul className="space-y-1">
              {result.limitations.map((limitation) => (
                <li key={limitation} className="text-xs text-amber-300/90">
                  · {limitation}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      )}
    </div>
  );
}
