import Link from "next/link";

import { EXTERNAL_ITEMS, RESOURCE_ITEMS } from "@/components/layout/nav-items";
import { Logo } from "@/components/ui/logo";
import { SITE_CONFIG } from "@/lib/site-config";

/**
 * Global footer spanning the full application width: the six project links
 * (GitHub, Documentation, Roadmap as external icons; Donate, License, About as
 * internal text links) plus version, license, and powered-by credit.
 */
export function Footer() {
  return (
    <footer className="flex shrink-0 flex-wrap items-center gap-x-4 gap-y-2 border-t bg-background px-4 py-2 text-xs text-muted-foreground">
      <div className="flex min-w-0 items-center gap-2">
        <Logo className="size-4 shrink-0" />
        <span className="hidden truncate font-medium text-foreground sm:inline">
          {SITE_CONFIG.name}
        </span>
      </div>

      <span className="hidden min-w-0 truncate md:inline">
        v{SITE_CONFIG.version} · {SITE_CONFIG.license} License · Powered by{" "}
        {SITE_CONFIG.company}
      </span>

      <div className="ml-auto flex flex-wrap items-center gap-x-4 gap-y-2">
        {EXTERNAL_ITEMS.map((item) => (
          <a
            key={item.label}
            href={item.href}
            target="_blank"
            rel="noreferrer"
            title={item.label}
            aria-label={`${item.label} (opens in a new tab)`}
            className="flex items-center gap-1 text-muted-foreground transition-colors hover:text-foreground"
          >
            <item.icon className="size-4" aria-hidden />
          </a>
        ))}
        {RESOURCE_ITEMS.map((item) => (
          <Link
            key={item.label}
            href={item.href}
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            {item.label}
          </Link>
        ))}
      </div>
    </footer>
  );
}
