import { Network } from "lucide-react";

import type { NetworkInterface } from "@/lib/dashboard";
import { isWan } from "@/lib/dashboard-utils";
import { InterfaceWidget } from "@/components/dashboard/interface-widget";

type Props = { network: NetworkInterface[] };

export function LanWidget({ network }: Props) {
  const lan = network.filter((iface) => !isWan(iface));
  return (
    <InterfaceWidget
      title="LAN"
      icon={Network}
      interfaces={lan}
      subtitle={lan.length === 0 ? "No local network detected" : "Local network"}
    />
  );
}
