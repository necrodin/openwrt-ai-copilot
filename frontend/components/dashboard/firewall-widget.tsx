import { Shield } from "lucide-react";

import type { FirewallInfo } from "@/lib/dashboard";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = { firewall: FirewallInfo };

function policyVariant(policy: string | null) {
  if (policy === "ACCEPT") {
    return "default" as const;
  }
  if (policy === "REJECT" || policy === "DROP") {
    return "destructive" as const;
  }
  return "secondary" as const;
}

export function FirewallWidget({ firewall }: Props) {
  if (firewall.zones.length === 0) {
    return (
      <Widget title="Firewall" icon={Shield}>
        <EmptyState message="No firewall zones found." />
      </Widget>
    );
  }

  return (
    <Widget
      title="Firewall"
      icon={Shield}
      subtitle={`${firewall.zones.length} zones · ${firewall.rules.length} rules`}
    >
      <ul className="space-y-2">
        {firewall.zones.map((zone) => (
          <li
            key={zone.name}
            className="rounded-md border px-3 py-2"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-sm font-medium">{zone.name}</span>
              {zone.masquerade ? (
                <Badge variant="outline">masquerade</Badge>
              ) : null}
            </div>
            <dl className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-muted-foreground">
              <div className="flex items-center gap-1.5">
                <span>In</span>
                <Badge variant={policyVariant(zone.input)}>{zone.input ?? "—"}</Badge>
              </div>
              <div className="flex items-center gap-1.5">
                <span>Out</span>
                <Badge variant={policyVariant(zone.output)}>{zone.output ?? "—"}</Badge>
              </div>
              <div className="flex items-center gap-1.5">
                <span>Fwd</span>
                <Badge variant={policyVariant(zone.forward)}>{zone.forward ?? "—"}</Badge>
              </div>
            </dl>
          </li>
        ))}
      </ul>
    </Widget>
  );
}
