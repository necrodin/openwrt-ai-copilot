import { Activity } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function MonitoringPage() {
  return (
    <ComingSoon
      title="Monitoring"
      icon={Activity}
      description="Historical graphs, alerts, and uptime trends will be collected here for each device."
    />
  );
}
