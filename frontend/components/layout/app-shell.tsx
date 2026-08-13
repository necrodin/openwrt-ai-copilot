"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { CopilotPanel } from "@/components/layout/copilot-panel";
import { Footer } from "@/components/layout/footer";
import { TopNav } from "@/components/layout/top-nav";

/**
 * Console shell with exactly three layers:
 *
 *   1. TOP NAVIGATION   — branding, primary nav, status/account actions.
 *   2. MAIN CONTENT     — the page plus the AI Copilot (part of main content,
 *                         expanded on the dashboard, collapsible elsewhere).
 *   3. GLOBAL FOOTER    — project links and version/license/powered-by.
 *
 * No left sidebar. The Copilot stays mounted so chat/session state survives
 * navigation; route changes re-apply the route's default Copilot state.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [copilotOverride, setCopilotOverride] = useState<boolean | null>(null);

  // Re-apply the route's default Copilot state on every navigation.
  useEffect(() => {
    setCopilotOverride(null);
  }, [pathname]);

  const isDashboard = pathname === "/dashboard";
  const copilotExpanded = copilotOverride ?? isDashboard;
  const toggleCopilot = () =>
    setCopilotOverride((previous) => !(previous ?? isDashboard));

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background text-foreground">
      <TopNav />

      <div className="flex min-h-0 flex-1">
        <main className="min-w-0 flex-1 overflow-y-auto">{children}</main>
        {/* AI Copilot — part of main content, route-aware expansion */}
        <CopilotPanel expanded={copilotExpanded} onToggle={toggleCopilot} />
      </div>

      <Footer />
    </div>
  );
}
