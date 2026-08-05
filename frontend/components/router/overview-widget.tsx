import { Router } from "lucide-react";

import type { DeviceSnapshot } from "@/lib/dashboard";
import { formatClock, formatDuration } from "@/lib/dashboard-utils";
import { InfoItem } from "@/components/router/info-item";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  snapshot: DeviceSnapshot | null;
  loading?: boolean;
  error?: string | null;
};

function na(value: string | null | undefined): string | null {
  return value && value.trim() !== "" ? value : null;
}

/**
 * Router identity panel: hostname, model, vendor, architecture, board,
 * firmware, kernel, build, uptime and last collected local time. Every value
 * maps to fields already served by the snapshot collectors — fields the
 * backend does not collect yet (vendor) render as "—" instead of being
 * invented.
 */
export function RouterOverviewWidget({ snapshot, loading = false, error = null }: Props) {
  if (snapshot === null) {
    return (
      <Widget title="Overview" icon={Router} loading={loading} error={error}>
        <EmptyState message="No device snapshot yet." />
      </Widget>
    );
  }

  const kernel = snapshot.kernel;
  const meta = snapshot.meta;
  const uptimeSeconds = snapshot.cpu?.uptime_seconds ?? null;
  const rows = [
    { label: "Hostname", value: na(kernel.hostname), mono: true },
    { label: "Model", value: na(kernel.model) || na(meta.model) },
    { label: "Vendor", value: null },
    { label: "Architecture", value: na(kernel.architecture), mono: true },
    { label: "Board", value: na(kernel.board) || na(meta.board) },
    { label: "Firmware", value: na(meta.firmware) || na(kernel.version) },
    { label: "Kernel", value: na(kernel.kernel), mono: true },
    { label: "Build", value: na(kernel.release), mono: true },
    { label: "Uptime", value: uptimeSeconds != null ? formatDuration(uptimeSeconds) : null, mono: true },
    { label: "Local Time", value: na(meta.collected_at) ? formatClock(meta.collected_at) : null, mono: true },
  ];

  return (
    <Widget
      title="Overview"
      icon={Router}
      subtitle={meta.collected_at ? `Last collected ${formatClock(meta.collected_at)}` : undefined}
      loading={loading}
      error={error}
    >
      <dl className="grid grid-cols-2 gap-x-6 gap-y-4 sm:grid-cols-3 xl:grid-cols-5">
        {rows.map((row) => (
          <InfoItem
            key={row.label}
            label={row.label}
            value={row.value}
            mono={row.mono}
          />
        ))}
      </dl>
    </Widget>
  );
}