import { Lock } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function VpnPage() {
  return (
    <ComingSoon
      title="VPN"
      icon={Lock}
      description="WireGuard and OpenVPN tunnels, peers, and status will be managed here."
    />
  );
}
