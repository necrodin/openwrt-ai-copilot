import type { ReactNode } from "react";

import { cn } from "@/lib/utils";

type WidgetGridProps = {
  children: ReactNode;
  className?: string;
};

/**
 * Responsive dashboard grid. Widgets may opt into wider spans via their own
 * `className` (e.g. `lg:col-span-2`).
 */
export function WidgetGrid({ children, className }: WidgetGridProps) {
  return (
    <div
      className={cn(
        "grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3",
        className,
      )}
    >
      {children}
    </div>
  );
}
