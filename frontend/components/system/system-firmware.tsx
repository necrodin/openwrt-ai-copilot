"use client";

import { Download } from "lucide-react";

import type { SystemInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";

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

export function SystemFirmware({ system }: Props) {
  return (
    <Card>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Download className="size-4 text-muted-foreground" aria-hidden />
          <h3 className="text-sm font-semibold">Firmware</h3>
        </div>
        <div className="divide-y">
          <Row label="Installed" value={system.firmware} />
          <Row label="Build date" value={system.build_date} />
          <Row label="Release" value={system.release} />
          <Row label="Revision" value={system.revision} />
        </div>
      </CardContent>
    </Card>
  );
}