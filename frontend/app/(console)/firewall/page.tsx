import { Shield } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function FirewallPage() {
  return (
    <ComingSoon
      title="Firewall"
      icon={Shield}
      description="Zones, policies, and rule management will be centralized here."
    />
  );
}
