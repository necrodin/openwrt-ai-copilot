import { cn } from "@/lib/utils";

type InfoItemProps = {
  label: string;
  value: React.ReactNode;
  /** Render the value in a monospace font (good for IPs, hashes, versions). */
  mono?: boolean;
  className?: string;
};

/**
 * A single label/value row used by the router identity panel. Keeping this as a
 * tiny dedicated component lets Overview render a uniform grid without
 * duplicating markup in every row.
 */
export function InfoItem({ label, value, mono = false, className }: InfoItemProps) {
  const text = value ?? "—";
  return (
    <dl className={cn("min-w-0 space-y-0.5", className)}>
      <dt className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">
        {label}
      </dt>
      <dd
        className={cn(
          "truncate text-sm font-medium text-foreground",
          mono && "font-mono tabular-nums",
        )}
        title={typeof text === "string" ? text : undefined}
      >
        {text}
      </dd>
    </dl>
  );
}