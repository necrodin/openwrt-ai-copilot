import { Github } from "lucide-react";

import { HealthStatus } from "@/components/health-status";
import { Logo } from "@/components/ui/logo";
import { SITE_CONFIG } from "@/lib/site-config";

/**
 * Compact enterprise footer: a single 48px bar pinned to the bottom of the
 * shell. Contains only the product name, version, license, powered-by credit,
 * a GitHub link, and the live health indicator. All project links live in the
 * sidebar's secondary navigation — see `sidebar.tsx`.
 */
export function Footer() {
  return (
    <footer className="flex h-12 shrink-0 items-center gap-3 border-t bg-background px-4 text-xs text-muted-foreground">
      <div className="flex min-w-0 items-center gap-2">
        <Logo className="size-4 shrink-0" />
        <span className="hidden truncate font-medium text-foreground sm:inline">
          {SITE_CONFIG.name}
        </span>
      </div>

      <span className="hidden min-w-0 flex-1 truncate text-center md:inline">
        v{SITE_CONFIG.version} · {SITE_CONFIG.license} License · Powered by{" "}
        {SITE_CONFIG.company}
      </span>

      <div className="flex shrink-0 items-center gap-3">
        <a
          href={SITE_CONFIG.repositoryUrl}
          target="_blank"
          rel="noreferrer"
          aria-label="OpenWrt AI Copilot on GitHub"
          title="OpenWrt AI Copilot on GitHub"
          className="text-muted-foreground transition-colors hover:text-foreground"
        >
          <Github className="size-4" aria-hidden />
        </a>
        <HealthStatus />
      </div>
    </footer>
  );
}
