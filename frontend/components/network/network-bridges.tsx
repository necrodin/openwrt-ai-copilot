"use client";

import { Network } from "lucide-react";

import type { NetworkInterface } from "@/lib/dashboard";
import { EmptyState } from "@/components/dashboard/widget";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { Badge } from "@/components/ui/badge";

type Props = {
  bridges: NetworkInterface[];
};

export function NetworkBridges({ bridges }: Props) {
  if (bridges.length === 0) {
    return (
      <div className="rounded-xl border py-10">
        <EmptyState message="No bridge interfaces detected." />
      </div>
    );
  }

  return (
    <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
      {bridges.map((bridge) => (
        <Card key={bridge.device ?? bridge.name}>
          <CardContent className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-base font-semibold">
                <Network className="size-4 text-muted-foreground" aria-hidden />
                {bridge.device ?? bridge.name}
              </h3>
              <StatusBadge
                label={bridge.up ? "Up" : "Down"}
                tone={bridge.up ? "success" : "danger"}
                dot
              />
            </div>
            {bridge.bridge_members.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {bridge.bridge_members.map((member) => (
                  <Badge key={member} variant="secondary">
                    {member}
                  </Badge>
                ))}
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">No members attached</p>
            )}
            <dl className="space-y-1.5 text-sm">
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">Interface</dt>
                <dd className="font-medium">{bridge.name || "—"}</dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">STP</dt>
                <dd className="font-medium">
                  {bridge.stp_enabled === null || bridge.stp_enabled === undefined
                    ? "—"
                    : bridge.stp_enabled
                      ? "Enabled"
                      : "Disabled"}
                </dd>
              </div>
              <div className="flex items-center justify-between">
                <dt className="text-muted-foreground">Forward delay</dt>
                <dd className="font-medium">
                  {bridge.forward_delay != null ? `${bridge.forward_delay}s` : "—"}
                </dd>
              </div>
            </dl>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}