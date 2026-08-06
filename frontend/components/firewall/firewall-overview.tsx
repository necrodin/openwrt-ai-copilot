"use client";

import { Activity, ShieldCheck, SlidersHorizontal } from "lucide-react";

import type { FirewallInfo } from "@/lib/dashboard";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { PolicyBadge } from "@/components/firewall/policy-badge";

type Props = {
  firewall: FirewallInfo;
};

function conntrackUsage(firewall: FirewallInfo): number | null {
  const { count, max } = firewall.conntrack ?? {};
  if (count == null || !max) {
    return null;
  }
  return Math.round((count / max) * 100);
}

export function FirewallOverview({ firewall }: Props) {
  const status = firewall.status;
  const usage = conntrackUsage(firewall);

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <ShieldCheck className="size-4 text-muted-foreground" />
            Default Policy
          </CardTitle>
        </CardHeader>
        <CardContent>
          {firewall.defaults ? (
            <dl className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">Input</dt>
                <dd>
                  <PolicyBadge value={firewall.defaults.input} />
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">Output</dt>
                <dd>
                  <PolicyBadge value={firewall.defaults.output} />
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">Forward</dt>
                <dd>
                  <PolicyBadge value={firewall.defaults.forward} />
                </dd>
              </div>
            </dl>
          ) : (
            <p className="text-sm text-muted-foreground">No defaults defined.</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <SlidersHorizontal className="size-4 text-muted-foreground" />
            Extras
          </CardTitle>
        </CardHeader>
        <CardContent>
          <ul className="space-y-2 text-sm">
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">Masquerade</span>
              <StatusBadge
                label={firewall.defaults?.masquerade ? "On" : "Off"}
                tone={firewall.defaults?.masquerade ? "success" : "neutral"}
                dot={false}
              />
            </li>
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">SYN flood</span>
              <StatusBadge
                label={firewall.defaults?.syn_flood ? "On" : "Off"}
                tone={firewall.defaults?.syn_flood ? "success" : "neutral"}
                dot={false}
              />
            </li>
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">OSF</span>
              <StatusBadge
                label={firewall.defaults?.osf ? "On" : "Off"}
                tone={firewall.defaults?.osf ? "success" : "neutral"}
                dot={false}
              />
            </li>
            <li className="flex items-center justify-between">
              <span className="text-muted-foreground">MTU</span>
              <span className="font-medium">
                {firewall.defaults?.mtu != null ? `${firewall.defaults.mtu} B` : "—"}
              </span>
            </li>
          </ul>
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Activity className="size-4 text-muted-foreground" />
            Connections
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="space-y-2 text-sm">
            <div className="flex items-center justify-between">
              <span className="text-muted-foreground">Firewall</span>
              <div className="flex gap-2">
                <StatusBadge
                  label={status?.running ? "Running" : "Stopped"}
                  tone={status?.running ? "success" : "danger"}
                  dot
                />
                <StatusBadge
                  label={status?.enabled ? "Enabled" : "Disabled"}
                  tone={status?.enabled ? "success" : "danger"}
                  dot={false}
                />
              </div>
            </div>
            {status?.version ? (
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Backend</span>
                <span className="font-medium">{status.version}</span>
              </div>
            ) : null}
            {firewall.conntrack && usage !== null ? (
              <div className="space-y-1 pt-1">
                <div className="flex items-center justify-between">
                  <span className="text-muted-foreground">Conntrack</span>
                  <span className="font-medium">
                    {firewall.conntrack.count?.toLocaleString() ?? "—"} /{" "}
                    {firewall.conntrack.max?.toLocaleString() ?? "—"}
                  </span>
                </div>
                <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
                  <div
                    className={usage > 90 ? "h-full bg-destructive" : "h-full bg-primary"}
                    style={{ width: `${Math.min(usage, 100)}%` }}
                  />
                </div>
                <p className="text-xs text-muted-foreground">{usage}% of table used</p>
              </div>
            ) : null}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}