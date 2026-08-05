import type { LucideIcon } from "lucide-react";
import type { ReactNode } from "react";

import { cn } from "@/lib/utils";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { WidgetSkeleton } from "@/components/dashboard/widget-skeleton";

type WidgetProps = {
  title: string;
  icon: LucideIcon;
  subtitle?: string;
  children: ReactNode;
  className?: string;
  /** Render a skeleton body instead of `children`. */
  loading?: boolean;
  /** Render an error body instead of `children`. */
  error?: string | null;
  /** Optional action rendered in the card header. */
  action?: ReactNode;
};

/**
 * Shared dashboard widget shell. Every widget on the NOC dashboard delegates
 * to this so loading, error, empty, and content states stay consistent and are
 * never duplicated.
 */
export function Widget({
  title,
  icon: Icon,
  subtitle,
  children,
  className,
  loading = false,
  error = null,
  action,
}: WidgetProps) {
  return (
    <Card className={cn("gap-3 py-4 transition-colors", className)}>
      <CardHeader className="flex flex-row items-start justify-between gap-3 px-4 pb-0">
        <div className="space-y-1">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Icon className="size-4 text-muted-foreground" aria-hidden />
            {title}
          </CardTitle>
          {subtitle ? (
            <CardDescription className="text-xs">{subtitle}</CardDescription>
          ) : null}
        </div>
        {action ?? null}
      </CardHeader>
      <CardContent className="px-4">
        {loading ? (
          <WidgetSkeleton />
        ) : error ? (
          <WidgetError message={error} />
        ) : (
          children
        )}
      </CardContent>
    </Card>
  );
}

export function WidgetError({ message }: { message: string }) {
  return (
    <div className="space-y-1">
      <p className="text-sm font-medium text-destructive">Failed to load</p>
      <p className="text-sm text-muted-foreground">{message}</p>
    </div>
  );
}

export function EmptyState({ message }: { message: string }) {
  return <p className="text-sm text-muted-foreground">{message}</p>;
}
