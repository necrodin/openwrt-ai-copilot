import { Stethoscope } from "lucide-react";

import type { RouterFinding } from "@/lib/dashboard-api";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  findings: RouterFinding[];
  loading?: boolean;
  error?: string | null;
};

function findingVariant(severity: string): "default" | "secondary" | "destructive" | "outline" {
  if (severity === "critical") return "destructive";
  if (severity === "warning") return "outline";
  return "secondary";
}

export function DiagnosisWidget({ findings, loading = false, error = null }: Props) {
  return (
    <Widget
      title="Latest Diagnosis"
      icon={Stethoscope}
      subtitle={findings.length === 0 ? "No issues detected" : `${findings.length} finding${findings.length === 1 ? "" : "s"}`}
      loading={loading}
      error={error}
    >
      {findings.length === 0 ? (
        <EmptyState message="The router looks healthy — no issues detected." />
      ) : (
        <ul className="max-h-72 space-y-2 overflow-y-auto">
          {findings.map((finding, index) => (
            <li
              key={`${finding.title}-${index}`}
              className="space-y-1 rounded-md border px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <Badge variant={findingVariant(finding.severity)}>
                  {finding.severity}
                </Badge>
                <span className="truncate text-sm font-medium">{finding.title}</span>
              </div>
              <p className="text-xs text-muted-foreground">{finding.description}</p>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
