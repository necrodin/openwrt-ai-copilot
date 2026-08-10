"use client";

import { Activity, Menu } from "lucide-react";

import { LogoutButton } from "@/components/auth/logout-button";
import { HealthStatus } from "@/components/health-status";
import { ThemeToggle } from "@/components/ui/theme-toggle";

type HeaderProps = {
  /** Rendered as a mobile menu trigger when provided. */
  onMenuClick?: () => void;
};

export function Header({ onMenuClick }: HeaderProps) {
  return (
    <header className="flex h-14 shrink-0 items-center justify-between gap-4 border-b bg-background/80 px-4 backdrop-blur">
      <div className="flex min-w-0 items-center gap-3">
        {onMenuClick ? (
          <button
            type="button"
            onClick={onMenuClick}
            className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground md:hidden"
            aria-label="Open navigation"
          >
            <Menu className="size-4" aria-hidden />
          </button>
        ) : null}
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Activity className="size-4" aria-hidden />
          <span className="hidden truncate sm:inline">Network Operations Center</span>
        </div>
      </div>
      <div className="flex shrink-0 items-center gap-2">
        <HealthStatus />
        <LogoutButton />
        <ThemeToggle />
      </div>
    </header>
  );
}
