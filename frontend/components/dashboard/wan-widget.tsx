import { Globe } from "lucide-react";

import type { NetworkInterface } from "@/lib/dashboard";
import { isWan } from "@/lib/dashboard-utils";
import { InterfaceWidget } from "@/components/dashboard/interface-widget";

type Props = { network: NetworkInterface[] };

export function WanWidget({ network }: Props) {
  const wan = network.filter(isWan);
  return (
    <InterfaceWidget
      title="WAN"
      icon={Globe}
      interfaces={wan}
      subtitle={wan.length === 0 ? "No uplink configured" : "Internet uplink"}
    />
  );
}
