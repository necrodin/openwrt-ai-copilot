"use client";

import { Cpu } from "lucide-react";

import type { SystemInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { formatBytes } from "@/lib/dashboard-utils";

type Props = {
  system: SystemInfo;
};

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="min-w-0 truncate text-right text-sm font-medium" title={value ?? ""}>
        {value || "N/A"}
      </span>
    </div>
  );
}

export function SystemInfoSection({ system }: Props) {
  const generatedAt = system.generated_at
    ? new Date(system.generated_at).toLocaleString()
    : null;

  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Cpu className="size-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-semibold">System information</h3>
        </div>
        <div className="divide-y">
          <Row label="CPU architecture" value={system.architecture} />
          <Row
            label="Endianness"
            value={system.endianness ? `${system.endianness} endian` : null}
          />
          <Row
            label="Flash size"
            value={system.flash_bytes != null ? formatBytes(system.flash_bytes) : null}
          />
          <Row label="Root filesystem" value={system.root_filesystem} />
          <Row label="Overlay filesystem" value={system.overlay_filesystem} />
          <Row label="Board vendor" value={system.vendor} />
          <Row label="Device tree" value={system.device_tree} />
          <Row label="Machine" value={system.machine} />
          <Row label="Board name" value={system.board} />
          <Row label="Collected" value={generatedAt} />
        </div>
      </CardContent>
    </Card>
  );
}