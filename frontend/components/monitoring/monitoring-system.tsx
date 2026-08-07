"use client";

import { CircuitBoard, Cpu, Server, Thermometer } from "lucide-react";

import type { DeviceSnapshot } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  snapshot: DeviceSnapshot;
};

const MONITORING_SERVICES = ["netdata", "collectd", "telegraf", "zabbix_agentd", "monit"];

function Row({ label, value }: { label: string; value: string | null }) {
  return (
    <div className="flex items-start justify-between gap-4 py-2">
      <span className="shrink-0 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </span>
      <span className="min-w-0 truncate text-right text-sm font-medium" title={value ?? ""}>
        {value ?? "—"}
      </span>
    </div>
  );
}

export function MonitoringSystem({ snapshot }: Props) {
  const { kernel, meta, temperature, services } = snapshot;

  const monitoring = services.filter((service) =>
    MONITORING_SERVICES.some((candidate) =>
      service.name.toLowerCase().includes(candidate.toLowerCase()),
    ),
  );

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Thermometer className="size-4 text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">Temperature</h3>
          </div>
          {temperature.length === 0 && (snapshot.cpu?.temperature_c ?? null) === null ? (
            <p className="rounded-md border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
              No temperature sensors detected.
            </p>
          ) : (
            <ul className="divide-y">
              {snapshot.cpu?.temperature_c != null ? (
                <li className="flex items-center justify-between py-2">
                  <span className="text-sm">CPU</span>
                  <span className="text-sm font-medium tabular-nums">
                    {snapshot.cpu.temperature_c.toFixed(1)}°C
                  </span>
                </li>
              ) : null}
              {temperature.map((zone) => (
                <li key={zone.zone} className="flex items-center justify-between py-2">
                  <span className="truncate text-sm">{zone.zone}</span>
                  <span className="text-sm font-medium tabular-nums">
                    {zone.temperature_c.toFixed(1)}°C
                  </span>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Server className="size-4 text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">Device</h3>
          </div>
          <div className="divide-y">
            <Row label="Hostname" value={kernel.hostname} />
            <Row label="OpenWrt" value={meta.firmware || kernel.version} />
            <Row label="Model" value={meta.model || kernel.model} />
            <Row label="Board" value={meta.board || kernel.board} />
            <Row label="Architecture" value={kernel.architecture} />
            <Row label="System" value={kernel.system} />
            <Row label="Kernel" value={kernel.kernel || kernel.release} />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <Cpu className="size-4 text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">Processor</h3>
          </div>
          <div className="divide-y">
            <Row label="CPU model" value={snapshot.cpu?.model ?? null} />
            <Row label="Cores" value={snapshot.cpu ? String(snapshot.cpu.cores) : null} />
            <Row
              label="Frequency"
              value={
                snapshot.cpu?.frequency_mhz != null
                  ? `${Math.round(snapshot.cpu.frequency_mhz)} MHz`
                  : null
              }
            />
          </div>
        </CardContent>
      </Card>

      <Card>
        <CardContent className="space-y-4">
          <div className="flex items-center gap-2">
            <CircuitBoard className="size-4 text-muted-foreground" aria-hidden />
            <h3 className="text-sm font-semibold">Monitoring services</h3>
          </div>
          {monitoring.length === 0 ? (
            <p className="rounded-md border border-dashed px-3 py-6 text-center text-sm text-muted-foreground">
              No monitoring daemon detected. The Restart Monitoring action will
              target whichever daemon is installed (netdata, collectd, telegraf…).
            </p>
          ) : (
            <ul className="space-y-2">
              {monitoring.map((service) => (
                <li key={service.name} className="flex items-center justify-between gap-2">
                  <span className="truncate text-sm font-medium">{service.name}</span>
                  <div className="flex items-center gap-2">
                    {service.enabled ? (
                      <span className="text-xs text-muted-foreground">enabled</span>
                    ) : null}
                    <StatusBadge
                      tone={service.running ? "success" : "warning"}
                      label={service.running ? "Running" : "Stopped"}
                    />
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}