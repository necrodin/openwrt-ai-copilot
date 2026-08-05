import { ExternalLink, type LucideIcon } from "lucide-react";

import { buttonVariants } from "@/components/ui/button";
import { cn } from "@/lib/utils";

/**
 * Button-styled link. Renders an inline anchor that looks like a Button;
 * external links open in a new tab with a trailing external-link icon for
 * clarity and accessibility.
 */

type LinkButtonProps = {
  href: string;
  children: React.ReactNode;
  external?: boolean;
  icon?: LucideIcon;
  variant?: "default" | "outline" | "ghost" | "secondary" | "link";
  className?: string;
};

export function LinkButton({
  href,
  children,
  external = false,
  icon: Icon,
  variant = "default",
  className,
}: LinkButtonProps) {
  const target = external ? { target: "_blank", rel: "noreferrer" } : {};
  return (
    <a
      href={href}
      {...target}
      className={cn(buttonVariants({ variant }), "justify-start", className)}
    >
      {Icon ? <Icon className="size-4" aria-hidden /> : null}
      <span className="truncate">{children}</span>
      {external ? (
        <ExternalLink className="ml-auto size-3.5 opacity-60" aria-hidden />
      ) : null}
    </a>
  );
}
