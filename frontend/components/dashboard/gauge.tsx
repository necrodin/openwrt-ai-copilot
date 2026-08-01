import { cn } from "@/lib/utils";

type GaugeProps = {
  value: number;
  max?: number;
  tone?: "neutral" | "good" | "warn" | "danger";
  className?: string;
};

function toneClass(tone: NonNullable<GaugeProps["tone"]>): string {
  switch (tone) {
    case "good":
      return "bg-emerald-500";
    case "warn":
      return "bg-amber-500";
    case "danger":
      return "bg-red-500";
    default:
      return "bg-primary";
  }
}

export function Gauge({ value, max = 100, tone = "neutral", className }: GaugeProps) {
  const ratio = max > 0 ? Math.max(0, Math.min(100, (value / max) * 100)) : 0;
  return (
    <div
      className={cn("h-2 w-full overflow-hidden rounded-full bg-muted", className)}
      role="progressbar"
      aria-valuenow={Math.round(value)}
      aria-valuemin={0}
      aria-valuemax={max}
    >
      <div
        className={cn("h-full rounded-full transition-[width] duration-700", toneClass(tone))}
        style={{ width: `${ratio}%` }}
      />
    </div>
  );
}
