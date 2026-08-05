import { GitBranch, Github, Zap } from "lucide-react";

import { Logo } from "@/components/ui/logo";
import { SITE_CONFIG } from "@/lib/site-config";

type FooterProps = {
  /** Hide the "powered by" strip (e.g. very compact layouts). */
  minimal?: boolean;
};

const poweredBy = [
  { label: "Necrodin", href: SITE_CONFIG.socials.github },
  { label: "OpenWrt", href: "https://openwrt.org" },
  { label: "FastAPI", href: "https://fastapi.tiangolo.com" },
  { label: "Next.js", href: "https://nextjs.org" },
  { label: "TailwindCSS", href: "https://tailwindcss.com" },
];

const resources = [
  { label: "About", href: "/about" },
  { label: "Support Development", href: "/support" },
  { label: "Roadmap", href: SITE_CONFIG.roadmapUrl },
  { label: "Changelog", href: SITE_CONFIG.changelogUrl },
];

const community = [
  { label: "GitHub", href: SITE_CONFIG.repositoryUrl },
  { label: "Issues", href: SITE_CONFIG.issuesUrl },
  { label: "Discussions", href: SITE_CONFIG.discussionsUrl },
  { label: "Documentation", href: SITE_CONFIG.documentationUrl },
];

export function Footer({ minimal = false }: FooterProps) {
  return (
    <footer className="border-t bg-background text-muted-foreground">
      <div className="mx-auto w-full max-w-7xl px-4 py-10 sm:px-6">
        <div className="grid gap-8 md:grid-cols-4">
          <div className="space-y-3 md:col-span-2">
            <Logo withText name={SITE_CONFIG.name} responsive />
            <p className="max-w-sm text-sm">{SITE_CONFIG.tagline}</p>
          </div>

          <nav aria-label="Project resources" className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Project
            </p>
            <ul className="space-y-2 text-sm">
              {resources.map((item) => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    className="transition-colors hover:text-foreground"
                  >
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>

          <nav aria-label="Community" className="space-y-3">
            <p className="text-xs font-semibold uppercase tracking-wider text-foreground">
              Community
            </p>
            <ul className="space-y-2 text-sm">
              {community.map((item) => (
                <li key={item.label}>
                  <a
                    href={item.href}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
                  >
                    {item.label === "GitHub" ? (
                      <Github className="size-3.5" aria-hidden />
                    ) : null}
                    {item.label}
                  </a>
                </li>
              ))}
            </ul>
          </nav>
        </div>

        {!minimal ? (
          <div className="mt-8 flex flex-wrap items-center gap-2 border-t pt-6">
            <span className="text-xs uppercase tracking-wider">Powered by</span>
            {poweredBy.map((tech) => (
              <a
                key={tech.label}
                href={tech.href}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs font-medium transition-colors hover:bg-accent hover:text-accent-foreground"
              >
                {tech.label}
              </a>
            ))}
          </div>
        ) : null}

        <div className="mt-6 flex flex-col justify-between gap-3 border-t pt-6 text-xs sm:flex-row sm:items-center">
          <p>
            © {new Date().getFullYear()} {SITE_CONFIG.name}. Released under the{" "}
            <span className="font-medium text-foreground">{SITE_CONFIG.license}</span>{" "}
            license.
          </p>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="inline-flex items-center gap-1.5">
              <Zap className="size-3.5" aria-hidden />
              v{SITE_CONFIG.version}
            </span>
            <span className="inline-flex items-center gap-1.5">
              <GitBranch className="size-3.5" aria-hidden />
              {SITE_CONFIG.gitCommit
                ? `build ${SITE_CONFIG.gitCommit}`
                : SITE_CONFIG.buildDate ?? "development build"}
            </span>
            <a
              href={SITE_CONFIG.repositoryUrl}
              target="_blank"
              rel="noreferrer"
              className="inline-flex items-center gap-1.5 transition-colors hover:text-foreground"
            >
              <Github className="size-3.5" aria-hidden />
              GitHub Repository
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
