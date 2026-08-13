"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { LogoutButton } from "@/components/auth/logout-button";
import { HealthStatus } from "@/components/health-status";
import { Logo } from "@/components/ui/logo";
import { ThemeToggle } from "@/components/ui/theme-toggle";
import {
  categoryActive,
  TOP_CATEGORIES,
  type NavCategory,
} from "@/components/layout/nav-items";
import { cn } from "@/lib/utils";
import { SITE_CONFIG } from "@/lib/site-config";

function CategoryLink({ category, pathname }: { category: NavCategory; pathname: string }) {
  if (category.type === "link") {
    const active = categoryActive(category, pathname);
    return (
      <Link
        href={category.href}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex shrink-0 items-center rounded-md px-3 py-2 text-sm font-medium transition-colors",
          active
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
        )}
      >
        {category.label}
      </Link>
    );
  }

  return <DropdownCategory category={category} pathname={pathname} />;
}

function DropdownCategory({
  category,
  pathname,
}: {
  category: Extract<NavCategory, { type: "dropdown" }>;
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement | null>(null);
  const active = categoryActive(category, pathname);

  useEffect(() => {
    if (!open) {
      return;
    }
    const onPointerDown = (event: MouseEvent) => {
      if (ref.current && !ref.current.contains(event.target as Node)) {
        setOpen(false);
      }
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [open]);

  return (
    <div ref={ref} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex items-center gap-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
          active
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
        )}
      >
        {category.label}
        <ChevronDown
          className={cn("size-3 transition-transform", open && "rotate-180")}
          aria-hidden
        />
      </button>

      {open ? (
        <div
          role="menu"
          aria-label={category.label}
          className="absolute left-0 top-full z-40 mt-1 w-48 rounded-md border bg-popover p-1 text-popover-foreground shadow-lg"
        >
          {category.items.map((item) => {
            const itemActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                role="menuitem"
                onClick={() => setOpen(false)}
                aria-current={itemActive ? "page" : undefined}
                className={cn(
                  "block rounded px-3 py-2 text-sm transition-colors",
                  itemActive
                    ? "bg-accent text-accent-foreground"
                    : "text-foreground hover:bg-accent/60 hover:text-accent-foreground",
                )}
              >
                {item.label}
              </Link>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Top navigation — the single top layer of the console shell. Shows only the
 * compact top-level categories; dropdown items open below their category.
 */
export function TopNav() {
  const pathname = usePathname();

  return (
    <header className="relative z-50 flex h-14 shrink-0 items-center gap-3 border-b bg-background/80 px-3 backdrop-blur">
      <Link
        href="/dashboard"
        aria-label={SITE_CONFIG.name}
        className="flex shrink-0 items-center gap-2"
      >
        <Logo withText responsive ariaHiddenText />
      </Link>

      <nav
        className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
        aria-label="Primary"
      >
        {TOP_CATEGORIES.map((category) => (
          <CategoryLink key={category.label} category={category} pathname={pathname} />
        ))}
      </nav>

      <div className="ml-auto flex shrink-0 items-center gap-2">
        <HealthStatus />
        <ThemeToggle />
        <LogoutButton />
      </div>
    </header>
  );
}
