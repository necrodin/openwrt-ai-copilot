"use client";

import {
  BookOpenText,
  Bug,
  DollarSign,
  ExternalLink,
  Github,
  Heart,
  Info,
  Map,
  Sparkles,
} from "lucide-react";
import Link from "next/link";

import { cn } from "@/lib/utils";
import { SITE_CONFIG } from "@/lib/site-config";

type LinkItem = {
  label: string;
  href: string;
  icon: typeof Github;
  external?: boolean;
};

const LINKS: LinkItem[] = [
  { label: "GitHub", href: SITE_CONFIG.repositoryUrl, icon: Github, external: true },
  { label: "Documentation", href: SITE_CONFIG.documentationUrl, icon: BookOpenText, external: true },
  { label: "Report Issue", href: SITE_CONFIG.issuesUrl, icon: Bug, external: true },
  { label: "Roadmap", href: SITE_CONFIG.roadmapUrl, icon: Map, external: true },
  { label: "License", href: "/about#license", icon: Sparkles },
  { label: "Donate", href: "/support", icon: Heart },
  { label: "About", href: "/about", icon: Info },
];

type SidebarOpenSourceProps = {
  collapsed: boolean;
};

/**
 * The "Open Source" section pinned at the bottom of the sidebar: a version
 * pill plus links to the repository, docs, issue tracker, roadmap, license,
 * donations, and the About page. When the sidebar is collapsed it renders as
 * icon-only so the row height stays compact.
 */
export function SidebarOpenSource({ collapsed }: SidebarOpenSourceProps) {
  return (
    <section className={cn("border-t", collapsed ? "p-1.5" : "p-2")} aria-label="Open source">
      {!collapsed ? (
        <Link
          href="/about"
          className="mb-1.5 flex items-center gap-2 rounded-md px-2 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground"
        >
          <span className="inline-flex items-center gap-1 text-foreground/80">
            <DollarSign className="size-3.5" aria-hidden />
            v{SITE_CONFIG.version}
          </span>
          <span className="text-[10px] uppercase tracking-wider">Open Source</span>
        </Link>
      ) : null}

      <ul className="space-y-0.5">
        {LINKS.map((item) => {
          const content = (
            <>
              <item.icon className="size-4 shrink-0" aria-hidden />
              {!collapsed ? (
                <>
                  <span className="truncate">{item.label}</span>
                  {item.external ? (
                    <ExternalLink className="ml-auto size-3 opacity-60" aria-hidden />
                  ) : null}
                </>
              ) : null}
            </>
          );
          const className = cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            collapsed && "justify-center px-0",
          );
          return (
            <li key={item.label}>
              {item.external ? (
                <a
                  href={item.href}
                  target="_blank"
                  rel="noreferrer"
                  className={className}
                  title={collapsed ? item.label : undefined}
                  aria-label={item.label}
                >
                  {content}
                </a>
              ) : (
                <Link
                  href={item.href}
                  className={className}
                  title={collapsed ? item.label : undefined}
                  aria-label={item.label}
                >
                  {content}
                </Link>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
