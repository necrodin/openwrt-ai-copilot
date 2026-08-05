import { cn } from "@/lib/utils";
import { Skeleton } from "@/components/ui/skeleton";

type WidgetSkeletonProps = {
  className?: string;
};

/**
 * Placeholder content shown inside a widget while its data is still loading.
 */
export function WidgetSkeleton({ className }: WidgetSkeletonProps) {
  return (
    <div
      className={cn("space-y-3", className)}
      aria-hidden
      data-slot="widget-skeleton"
    >
      <Skeleton className="h-8 w-16" />
      <Skeleton className="h-2 w-full" />
      <Skeleton className="h-2 w-4/5" />
      <div className="grid grid-cols-3 gap-2 pt-1">
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
        <Skeleton className="h-8" />
      </div>
    </div>
  );
}
