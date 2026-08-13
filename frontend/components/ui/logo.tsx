import { cn } from "@/lib/utils";

/**
 * Reusable brand logo. Renders the OpenWrt AI Copilot mark and, optionally,
 * the wordmark. The mark is an inline SVG so it inherits `currentColor`, scales
 * with its container, and renders crisply at any size.
 *
 * Use `<Logo withText />` in the top navigation and `<Logo />` alone for
 * compact spots (avatar, footer).
 */

type LogoProps = {
  /** CSS size classes for the mark (e.g. "size-8"). */
  className?: string;
  /** Show the wordmark next to the mark. */
  withText?: boolean;
  /** Text to render for the wordmark (defaults to the product name). */
  name?: string;
  /** Render the wordmark truncated / hidden on very small screens. */
  responsive?: boolean;
  /** Hide the wordmark from screen readers when it duplicates surrounding text. */
  ariaHiddenText?: boolean;
};

export function Logo({
  className,
  withText = false,
  name = "OpenWrt AI Copilot",
  responsive = false,
  ariaHiddenText = false,
}: LogoProps) {
  return (
    <span className={cn("inline-flex min-w-0 items-center gap-2", className)}>
      <Mark className="size-6 shrink-0" />
      {withText ? (
        <span
          className={cn(
            "truncate font-semibold tracking-tight",
            responsive && "hidden sm:inline",
          )}
          aria-hidden={ariaHiddenText || undefined}
        >
          {name}
        </span>
      ) : null}
    </span>
  );
}

type MarkProps = {
  className?: string;
};

/** The raw logo mark (SVG). Exported for use in favicons/banners/tests. */
export function Mark({ className }: MarkProps) {
  return (
    <svg
      viewBox="0 0 64 64"
      role="img"
      aria-label="OpenWrt AI Copilot logo"
      className={cn("text-foreground", className)}
    >
      <circle cx="32" cy="32" r="32" className="fill-primary/10" />
      <path
        d="M16 44a14 14 0 0 1 0-24"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        fill="none"
      />
      <path
        d="M22 40a8 8 0 0 1 0-16"
        stroke="currentColor"
        strokeWidth="4.5"
        strokeLinecap="round"
        fill="none"
        opacity="0.55"
      />
      <circle cx="32" cy="32" r="6" className="fill-current" />
      <path
        d="M48 44a14 14 0 0 0 0-24"
        stroke="currentColor"
        strokeWidth="4"
        strokeLinecap="round"
        fill="none"
        opacity="0.3"
      />
      <circle cx="48" cy="44" r="3.5" fill="currentColor" opacity="0.45" />
    </svg>
  );
}
