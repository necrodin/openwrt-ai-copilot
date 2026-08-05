import { Router } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function RoutersPage() {
  return (
    <ComingSoon
      title="Routers"
      icon={Router}
      description="Manage your router fleet — device inventory, credentials, and per-device status will live here."
    />
  );
}
