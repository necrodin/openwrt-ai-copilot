"use client";

import type { FirewallZone } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { PolicyBadge } from "@/components/firewall/policy-badge";

type Props = {
  zones: FirewallZone[];
  busy?: boolean;
  onToggle: (section: string, enabled: boolean) => void;
};

function zoneNetworks(zone: FirewallZone): string[] {
  if (zone.network == null) {
    return [];
  }
  return Array.isArray(zone.network) ? zone.network : [zone.network];
}

export function FirewallZones({ zones, busy = false, onToggle }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {zones.map((zone) => {
        const networks = zoneNetworks(zone);
        return (
          <Card key={zone.section}>
            <CardContent className="space-y-3">
              <div className="flex items-center justify-between">
                <h3 className="text-base font-semibold">{zone.name}</h3>
                <div className="flex items-center gap-1.5">
                  <Badge variant={zone.enabled ? "default" : "secondary"}>
                    {zone.enabled ? "enabled" : "disabled"}
                  </Badge>
                  {zone.family ? <Badge variant="outline">{zone.family}</Badge> : null}
                </div>
              </div>
              <div className="flex flex-wrap gap-1.5">
                {zone.masquerade ? <Badge variant="outline">masquerade</Badge> : null}
                {zone.mtu_fix ? <Badge variant="outline">mtu fix</Badge> : null}
              </div>
              {networks.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {networks.map((net) => (
                    <Badge key={net} variant="secondary">
                      {net}
                    </Badge>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">No networks attached</p>
              )}
              <dl className="space-y-1.5 text-sm">
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">Input</dt>
                  <dd>
                    <PolicyBadge value={zone.input} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">Output</dt>
                  <dd>
                    <PolicyBadge value={zone.output} />
                  </dd>
                </div>
                <div className="flex items-center justify-between">
                  <dt className="text-muted-foreground">Forward</dt>
                  <dd>
                    <PolicyBadge value={zone.forward} />
                  </dd>
                </div>
              </dl>
              <Button
                size="sm"
                variant={zone.enabled ? "outline" : "default"}
                disabled={busy}
                onClick={() => onToggle(zone.section, !zone.enabled)}
              >
                {zone.enabled ? "Disable" : "Enable"}
              </Button>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}