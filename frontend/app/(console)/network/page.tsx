import { Network } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function NetworkPage() {
  return (
    <ComingSoon
      title="Network"
      icon={Network}
      description="Interfaces, routes, DHCP leases, and ARP tables will be visualized here."
    />
  );
}
