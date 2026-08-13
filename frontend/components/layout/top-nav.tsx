"use client";

import { Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

import { LogoutButton } from "@/components/auth/logout-button";
import { HealthStatus } from "@/components/health-status";
import { Logo } from "@/components/ui/logo";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import { NAV_ITEMS, type NavItem } from "@/components/layout/nav-items";
import { cn } from "@/lib/utils";
import { SITE_CONFIG } from "@/lib/site-config";

function isActive(pathname: string, href: string): boolean {
  if (href === "/dashboard") {
    return pathname === href;
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

function NavLink({ item, pathname }: { item: NavItem; pathname: string }) {
  return (
    <Link
      href={item.href}
      aria-current={isActive(pathname, item.href) ? "page" : undefined}
      className={cn(
        "flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors",
        isActive(pathname, item.href)
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
      )}
    >
      <item.icon className="size-4 shrink-0" aria-hidden />
      <span className="truncate">{item.label}</span>
    </Link>
  );
}

/**
 * Top navigation — the single top layer of the console shell. Branding, the
 * primary operational navigation, and the session/status actions live in one
 * horizontal bar. On small screens the navigation collapses behind a menu.
 */
export function TopNav() {
  const pathname = usePathname();
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <header className="relative flex h-14 shrink-0 items-center gap-3 border-b bg-background/80 px-3 backdrop-blur">
      <Link
        href="/dashboard"
        aria-label={SITE_CONFIG.name}
        className="flex shrink-0 items-center gap-2"
      >
        <Logo withText responsive ariaHiddenText />
      </Link>

      <nav
        className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto lg:flex"
        aria-label="Primary"
      >
        {NAV_ITEMS.map((item) => (
          <NavLink key={item.href} item={item} pathname={pathname} />
        ))}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <HealthStatus />
        <ThemeToggle />
        <LogoutButton />
        <button
          type="button"
          onClick={() => setMenuOpen((value) => !value)}
          className="rounded-md p-2 text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground lg:hidden"
          aria-label="Toggle navigation"
          aria-expanded={menuOpen}
        >
          {menuOpen ? <X className="size-4" aria-hidden /> : <Menu className="size-4" aria-hidden />}
        </button>
      </div>

      {menuOpen ? (
        <div
          className="absolute inset-x-0 top-14 z-40 border-b bg-background shadow-lg lg:hidden"
          role="dialog"
          aria-label="Primary navigation"
        >
          <nav className="grid max-h-[70vh] grid-cols-2 gap-1 overflow-y-auto p-3" aria-label="Primary">
            {NAV_ITEMS.map((item) => (
              <NavLink key={item.href} item={item} pathname={pathname} />
            ))}
          </nav>
        </div>
      ) : null}
    </header>
  );
}
