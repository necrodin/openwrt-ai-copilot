import { Badge } from "@/components/ui/badge";

function policyVariant(policy: string | null) {
  if (policy === "ACCEPT") {
    return "default" as const;
  }
  if (policy === "REJECT" || policy === "DROP") {
    return "destructive" as const;
  }
  return "secondary" as const;
}

export function PolicyBadge({ value }: { value: string | null }) {
  return <Badge variant={policyVariant(value)}>{value ?? "—"}</Badge>;
}