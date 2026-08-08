"use client";

import { Boxes, Cable, FileCode2 } from "lucide-react";

import type { FirewallInfo } from "@/lib/router-management";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  firewall: FirewallInfo;
};

export function FirewallConfiguration({ firewall }: Props) {
  const { includes, ipsets, ipsets_available, interfaces } = firewall;

  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <FileCode2 className="size-4 text-muted-foreground" />
            Includes
          </CardTitle>
        </CardHeader>
        <CardContent>
          {includes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No custom includes configured.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {includes.map((include) => (
                <li
                  key={include.section}
                  className="flex items-center justify-between gap-2"
                >
                  <div className="min-w-0 space-y-0.5">
                    <p className="truncate font-medium">{include.name || include.path}</p>
                    {include.path ? (
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {include.path}
                      </p>
                    ) : null}
                  </div>
                  <Badge variant={include.enabled ? "default" : "secondary"}>
                    {include.enabled ? "enabled" : "disabled"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Boxes className="size-4 text-muted-foreground" />
            IP Sets
          </CardTitle>
        </CardHeader>
        <CardContent>
          {!ipsets_available ? (
            <p className="text-sm text-muted-foreground">
              The <code className="font-mono">ipset</code> package is not installed.
            </p>
          ) : ipsets.length === 0 ? (
            <p className="text-sm text-muted-foreground">No IP sets configured.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {ipsets.map((set) => (
                <li
                  key={set.section}
                  className="flex items-center justify-between gap-2"
                >
                  <div className="min-w-0 space-y-0.5">
                    <p className="truncate font-medium">
                      {set.name || "Unnamed set"}
                      {set.match ? (
                        <span className="ml-1 text-xs text-muted-foreground">
                          ({set.match})
                        </span>
                      ) : null}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {set.count} {set.count === 1 ? "entry" : "entries"}
                    </p>
                  </div>
                  <Badge variant={set.enabled ? "default" : "secondary"}>
                    {set.enabled ? "enabled" : "disabled"}
                  </Badge>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Cable className="size-4 text-muted-foreground" />
            Interfaces
          </CardTitle>
        </CardHeader>
        <CardContent>
          {interfaces.length === 0 ? (
            <p className="text-sm text-muted-foreground">No interfaces reported.</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {interfaces.map((iface) => (
                <li
                  key={iface.name}
                  className="flex items-center justify-between gap-2"
                >
                  <div className="min-w-0 space-y-0.5">
                    <p className="truncate font-medium">{iface.name}</p>
                    {iface.device ? (
                      <p className="truncate font-mono text-xs text-muted-foreground">
                        {iface.device}
                      </p>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    {iface.proto ? (
                      <Badge variant="outline">{iface.proto}</Badge>
                    ) : null}
                    <StatusBadge
                      label={iface.up ? "up" : "down"}
                      tone={iface.up ? "success" : "danger"}
                      dot
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