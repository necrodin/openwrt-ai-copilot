import { Wifi } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function WirelessPage() {
  return (
    <ComingSoon
      title="Wireless"
      icon={Wifi}
      description="Radio bands, channels, SSIDs, and station analytics will be shown here."
    />
  );
}
