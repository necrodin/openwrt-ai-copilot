"use client";

import type { FirewallZone } from "@/lib/dashboard";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { PolicyBadge } from "@/components/firewall/policy-badge";

type Props = {
  zones: FirewallZone[];
};

export function FirewallZones({ zones }: Props) {
  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
      {zones.map((zone) => (
        <Card key={zone.name}>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-base font-semibold">{zone.name}</h3>
              <div className="flex gap-1.5">
                {zone.masquerade ? <Badge variant="outline">masquerade</Badge> : null}
                {zone.mtu_fix ? <Badge variant="outline">mtu fix</Badge> : null}
              </div>
            </div>
            {zone.network.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {zone.network.map((net) => (
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
          </CardContent>
        </Card>
      ))}
    </div>
  );
}