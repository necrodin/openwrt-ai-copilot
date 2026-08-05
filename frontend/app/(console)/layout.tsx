import type { ReactNode } from "react";

import { AppShell } from "@/components/layout/app-shell";

/**
 * Console route group: wraps the persistent NOC shell (sidebar + header)
 * around every page under `/routers`, `/dashboard`, etc.
 */
export default function ConsoleLayout({ children }: { children: ReactNode }) {
  return <AppShell>{children}</AppShell>;
}
