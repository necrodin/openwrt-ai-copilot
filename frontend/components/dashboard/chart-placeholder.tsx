import { cn } from "@/lib/utils";

type ChartPlaceholderProps = {
  className?: string;
  label?: string;
};

/**
 * Reusable decorative chart used for empty/skeleton states. A static area line
 * so widgets look populated even before real telemetry arrives.
 */
export function ChartPlaceholder({ className, label }: ChartPlaceholderProps) {
  return (
    <div className={cn("flex flex-col gap-1.5", className)} aria-hidden>
      <svg
        viewBox="0 0 100 28"
        preserveAspectRatio="none"
        className="h-8 w-full text-muted-foreground/50"
      >
        <path
          d="M0 24 H12 L22 18 L32 20 L42 12 L52 14 L62 8 L72 10 L82 4 L92 6 L100 2 V28 H0 Z"
          fill="currentColor"
          opacity="0.12"
        />
        <path
          d="M0 24 H12 L22 18 L32 20 L42 12 L52 14 L62 8 L72 10 L82 4 L92 6 L100 2"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
          vectorEffect="non-scaling-stroke"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      {label ? <p className="text-xs text-muted-foreground">{label}</p> : null}
    </div>
  );
}
