import type { LucideIcon } from "lucide-react";

import { cn } from "@/lib/utils";

export type SectionTab = {
  id: string;
  label: string;
  icon?: LucideIcon;
};

type SectionTabsProps = {
  tabs: SectionTab[];
  active: string;
  onChange: (id: string) => void;
  className?: string;
};

/**
 * Responsive tab row used to switch between the router management sections.
 * Renders as an accessible button group of pills; the active tab is highlighted
 * and announced via `aria-current`.
 */
export function SectionTabs({ tabs, active, onChange, className }: SectionTabsProps) {
  return (
    <nav
      className={cn(
        "flex flex-wrap items-center gap-1.5 rounded-md border bg-muted/40 p-1",
        className,
      )}
      aria-label="Router management sections"
    >
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            onClick={() => onChange(tab.id)}
            aria-current={isActive ? "page" : undefined}
            className={cn(
              "inline-flex items-center gap-2 rounded-md px-3 py-1.5 text-sm font-medium transition-colors",
              isActive
                ? "bg-background text-foreground shadow-sm"
                : "text-muted-foreground hover:text-foreground",
            )}
          >
            {Icon ? <Icon className="size-4" aria-hidden /> : null}
            {tab.label}
          </button>
        );
      })}
    </nav>
  );
}