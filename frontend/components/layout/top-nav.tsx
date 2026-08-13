"use client";

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

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

const MENU_WIDTH = 192;

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

/**
 * Dropdown category rendered through a React portal to ``document.body``.
 *
 * The trigger lives inside the top navigation (whose ``overflow-x-auto`` nav
 * would otherwise clip an in-tree menu). Portaling the menu out of the header
 * subtree lets it overlay MAIN CONTENT with viewport-fixed positioning derived
 * from the trigger's bounding rect, so it is never clipped and stays clickable.
 */
function DropdownCategory({
  category,
  pathname,
}: {
  category: Extract<NavCategory, { type: "dropdown" }>;
  pathname: string;
}) {
  const [open, setOpen] = useState(false);
  const [position, setPosition] = useState<{ left: number; top: number } | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);
  const active = categoryActive(category, pathname);

  const measure = useCallback(() => {
    const el = triggerRef.current;
    if (!el) {
      return;
    }
    const rect = el.getBoundingClientRect();
    let left = rect.left;
    if (left + MENU_WIDTH > window.innerWidth) {
      left = Math.max(8, window.innerWidth - MENU_WIDTH - 8);
    }
    setPosition({ left, top: rect.bottom + 4 });
  }, []);

  const close = useCallback(() => setOpen(false), []);

  useEffect(() => {
    if (!open) {
      return;
    }
    measure();
    const onPointerDown = (event: MouseEvent) => {
      const target = event.target as Node;
      if (triggerRef.current?.contains(target) || menuRef.current?.contains(target)) {
        return;
      }
      close();
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        close();
      }
    };
    const onResize = () => measure();
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKeyDown);
    window.addEventListener("resize", onResize);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("resize", onResize);
    };
  }, [open, measure, close]);

  const menu =
    open && position ? (
      createPortal(
        <div
          ref={menuRef}
          role="menu"
          aria-label={category.label}
          style={{ left: position.left, top: position.top, width: MENU_WIDTH, zIndex: 60 }}
          className="fixed mt-1 rounded-md border bg-popover p-1 text-popover-foreground shadow-lg"
        >
          {category.items.map((item) => {
            const itemActive = pathname === item.href || pathname.startsWith(`${item.href}/`);
            return (
              <Link
                key={item.href}
                href={item.href}
                role="menuitem"
                onClick={close}
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
        </div>,
        document.body,
      )
    ) : null;

  return (
    <>
      <button
        ref={triggerRef}
        type="button"
        onClick={() => setOpen((value) => !value)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-current={active ? "page" : undefined}
        className={cn(
          "flex shrink-0 items-center gap-1 rounded-md px-3 py-2 text-sm font-medium transition-colors",
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
      {menu}
    </>
  );
}

/**
 * Top navigation — the single top layer of the console shell. Shows only the
 * compact top-level categories; dropdown items render through a portal so they
 * always overlay MAIN CONTENT without being clipped.
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
