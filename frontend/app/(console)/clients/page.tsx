import { MonitorSmartphone } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function ClientsPage() {
  return (
    <ComingSoon
      title="Clients"
      icon={MonitorSmartphone}
      description="Every device on the network — hosts, IPs, MACs, and signal strength — will be listed here."
    />
  );
}
