"use client";

import type { SystemInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { formatDuration } from "@/lib/dashboard-utils";

type Props = {
  system: SystemInfo;
};

function Tile({ label, value }: { label: string; value: string | null }) {
  return (
    <Card>
      <CardContent className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </p>
        <p className="truncate text-sm font-semibold" title={value ?? ""}>
          {value || "—"}
        </p>
      </CardContent>
    </Card>
  );
}

export function SystemOverview({ system }: Props) {
  const items = [
    { label: "Hostname", value: system.hostname },
    { label: "Model", value: system.model },
    { label: "Architecture", value: system.architecture },
    { label: "Target", value: system.target },
    { label: "Firmware", value: system.firmware },
    { label: "Kernel", value: system.kernel },
    { label: "Release", value: system.release },
    { label: "Board", value: system.board },
    { label: "Local time", value: system.local_time },
    {
      label: "Uptime",
      value:
        system.uptime_seconds != null ? formatDuration(system.uptime_seconds) : null,
    },
    { label: "Timezone", value: system.timezone || system.zonename },
    { label: "Language", value: system.language },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => (
        <Tile key={item.label} label={item.label} value={item.value} />
      ))}
    </div>
  );
}