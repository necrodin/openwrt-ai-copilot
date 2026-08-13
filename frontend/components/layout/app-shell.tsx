"use client";

import { useEffect, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";

import { CopilotPanel } from "@/components/layout/copilot-panel";
import { Header } from "@/components/layout/header";
import { Sidebar } from "@/components/layout/sidebar";
import { Footer } from "@/components/layout/footer";

/**
 * Persistent NOC-style shell: collapsible left sidebar (desktop), a drawer
 * sidebar on mobile, a top header, a scrollable content area, and the AI
 * Copilot panel on the right. Only wraps the console pages.
 *
 * The Copilot is a global console feature: it is expanded by default on the
 * dashboard and collapsed (a narrow strip) everywhere else, and it stays
 * mounted so chat/session state survives navigation. Route changes re-apply
 * the route's default state; the operator may expand/collapse at any time.
 */
export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [collapsed, setCollapsed] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
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
    <div className="relative flex h-dvh overflow-hidden bg-background text-foreground">
      {/* Desktop sidebar */}
      <div className="hidden md:block">
        <Sidebar
          collapsed={collapsed}
          onToggle={() => setCollapsed((value) => !value)}
        />
      </div>

      {/* Mobile drawer */}
      {mobileOpen ? (
        <div className="fixed inset-0 z-50 flex md:hidden" role="dialog" aria-modal="true">
          <div
            className="absolute inset-0 bg-black/50"
            onClick={() => setMobileOpen(false)}
            aria-hidden
          />
          <div className="relative h-full">
            <Sidebar collapsed={false} onToggle={() => setMobileOpen(false)} />
          </div>
        </div>
      ) : null}

      <div className="flex min-w-0 flex-1 flex-col">
        <Header onMenuClick={() => setMobileOpen(true)} />
        <main className="flex-1 overflow-y-auto">{children}</main>
        <Footer />
      </div>

      {/* AI Copilot — always mounted, route-aware expansion */}
      <CopilotPanel expanded={copilotExpanded} onToggle={toggleCopilot} />
    </div>
  );
}
