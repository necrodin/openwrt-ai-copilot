import { Settings } from "lucide-react";

import { ComingSoon } from "@/components/layout/coming-soon";

export default function SettingsPage() {
  return (
    <ComingSoon
      title="Settings"
      icon={Settings}
      description="Application preferences, provider configuration, and appearance options will live here."
    />
  );
}
