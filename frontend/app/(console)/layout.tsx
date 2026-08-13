import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";

/**
 * Console route group: wraps the three-layer shell (top navigation, main
 * content with the AI Copilot, and a global footer) around every console page.
 */
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
