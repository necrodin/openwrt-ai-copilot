import { Lightbulb } from "lucide-react";

import type { RouterRecommendation } from "@/lib/dashboard-api";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget } from "@/components/dashboard/widget";

type Props = {
  recommendations: RouterRecommendation[];
  loading?: boolean;
  error?: string | null;
};

function priorityVariant(priority: string): "default" | "secondary" | "destructive" | "outline" {
  if (priority === "urgent") return "destructive";
  if (priority === "high") return "outline";
  if (priority === "medium") return "secondary";
  return "default";
}

export function RecommendationsWidget({ recommendations, loading = false, error = null }: Props) {
  return (
    <Widget
      title="Recommendations"
      icon={Lightbulb}
      subtitle={recommendations.length === 0 ? "Nothing to do" : `${recommendations.length} suggestion${recommendations.length === 1 ? "" : "s"}`}
      loading={loading}
      error={error}
    >
      {recommendations.length === 0 ? (
        <EmptyState message="No recommended actions right now." />
      ) : (
        <ul className="max-h-72 space-y-2 overflow-y-auto">
          {recommendations.map((recommendation) => (
            <li key={recommendation.id} className="space-y-1 rounded-md border px-3 py-2">
              <div className="flex items-center gap-2">
                <Badge variant={priorityVariant(recommendation.priority)}>
                  {recommendation.priority}
                </Badge>
                <span className="truncate text-sm font-medium">{recommendation.title}</span>
              </div>
              <p className="text-xs text-muted-foreground">{recommendation.description}</p>
            </li>
          ))}
        </ul>
      )}
    </Widget>
  );
}
