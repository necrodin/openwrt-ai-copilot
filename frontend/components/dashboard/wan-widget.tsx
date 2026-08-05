import { Globe } from "lucide-react";

import type { NetworkInterface } from "@/lib/dashboard";
import { isWan } from "@/lib/dashboard-utils";
import { InterfaceWidget } from "@/components/dashboard/interface-widget";

type Props = {
  network: NetworkInterface[];
  loading?: boolean;
  error?: string | null;
};

export function WanWidget({ network, loading, error }: Props) {
  const wan = network.filter(isWan);
  return (
    <InterfaceWidget
      title="WAN"
      icon={Globe}
      interfaces={wan}
      subtitle={wan.length === 0 ? "No uplink configured" : "Internet uplink"}
      loading={loading}
      error={error}
    />
  );
}
