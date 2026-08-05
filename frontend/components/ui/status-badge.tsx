import { cn } from "@/lib/utils";

/**
 * Tone that drives both the badge background and its indicator dot.
 */
export type StatusBadgeTone =
  | "neutral"
  | "success"
  | "warning"
  | "danger"
  | "info";

type StatusBadgeProps = {
  label: string;
  tone?: StatusBadgeTone;
  /** Show a small colored status dot. Defaults to true. */
  dot?: boolean;
  className?: string;
};

const toneClasses: Record<StatusBadgeTone, string> = {
  neutral: "border-border bg-muted text-muted-foreground",
  success:
    "border-emerald-500/40 bg-emerald-500/10 text-emerald-700 dark:text-emerald-400",
  warning: "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
  danger: "border-destructive/40 bg-destructive/10 text-destructive",
  info: "border-sky-500/40 bg-sky-500/10 text-sky-700 dark:text-sky-400",
};

const dotClasses: Record<StatusBadgeTone, string> = {
  neutral: "bg-muted-foreground",
  success: "bg-emerald-500",
  warning: "bg-amber-500",
  danger: "bg-destructive",
  info: "bg-sky-500",
};

/**
 * Reusable status badge with a consistent tone system (success/warning/danger /
 * info/neutral) and an optional indicator dot. Used across dashboard widgets.
 */
export function StatusBadge({
  label,
  tone = "neutral",
  dot = true,
  className,
}: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 whitespace-nowrap rounded-md border px-2 py-0.5 text-xs font-medium",
        toneClasses[tone],
        className,
      )}
    >
      {dot ? (
        <span className={cn("size-1.5 shrink-0 rounded-full", dotClasses[tone])} aria-hidden />
      ) : null}
      {label}
    </span>
  );
}
