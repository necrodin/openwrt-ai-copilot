"use client";

import type { WifiRadio } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { StatusBadge } from "@/components/ui/status-badge";
import { useState } from "react";

type Props = {
  radios: WifiRadio[];
  busy?: boolean;
  onToggle?: (section: string, enabled: boolean) => void;
};

type PendingToggle = { section: string; name: string; enabled: boolean } | null;

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

export function WirelessRadios({ radios, busy = false, onToggle }: Props) {
  const [pending, setPending] = useState<PendingToggle>(null);

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {radios.map((radio) => (
        <Card key={radio.section || radio.name}>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <h3 className="font-semibold">{radio.name}</h3>
                {radio.band ? <Badge variant="outline">{radio.band}</Badge> : null}
              </div>
              <StatusBadge
                label={radio.up ? "Up" : "Down"}
                tone={radio.up ? "success" : "danger"}
                dot
              />
            </div>
            {radio.hardware ? (
              <p className="text-xs text-muted-foreground">{radio.hardware}</p>
            ) : null}
            <dl className="space-y-1.5">
              <Row label="Device" value={radio.name} />
              <Row
                label="Channel"
                value={
                  radio.channel
                    ? `${radio.channel}${radio.frequency_mhz ? ` (${radio.frequency_mhz} MHz)` : ""}`
                    : "—"
                }
              />
              <Row label="Width" value={radio.width_mhz ? `${radio.width_mhz} MHz` : "—"} />
              <Row label="Country" value={radio.country ?? "—"} />
              <Row
                label="TX Power"
                value={radio.tx_power != null ? `${radio.tx_power} dBm` : "—"}
              />
              <Row label="Mode" value={radio.hwmode ?? radio.mode ?? "—"} />
              <Row label="SSID" value={radio.ssid ?? "—"} />
              <Row label="Stations" value={String(radio.station_count)} />
            </dl>
            {onToggle ? (
              <>
                <div className="flex items-center justify-between border-t pt-3">
                  <span className="text-sm text-muted-foreground">
                    {radio.enabled ? "Enabled" : "Disabled"}
                  </span>
                  <Button
                    size="sm"
                    variant={radio.enabled ? "destructive" : "default"}
                    disabled={busy}
                    onClick={() =>
                      setPending({
                        section: radio.section,
                        name: radio.name,
                        enabled: !radio.enabled,
                      })
                    }
                  >
                    {radio.enabled ? "Disable" : "Enable"}
                  </Button>
                </div>
              </>
            ) : null}
          </CardContent>
        </Card>
      ))}

      <ConfirmDialog
        open={pending !== null}
        title={
          pending
            ? `${pending.enabled ? "Enable" : "Disable"} radio \u201c${pending.name}\u201d?`
            : ""
        }
        description={
          pending
            ? pending.enabled
              ? "The radio hardware will be turned on and its SSIDs will become available again."
              : "The radio hardware and all of its SSIDs will stop. Clients on this band will disconnect."
            : ""
        }
        confirmLabel={pending ? (pending.enabled ? "Enable" : "Disable") : ""}
        busy={busy}
        onConfirm={() => {
          if (pending) {
            onToggle?.(pending.section, pending.enabled);
          }
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </div>
  );
}