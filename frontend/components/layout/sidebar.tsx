"use client";

import {
  Activity,
  BookOpenText,
  Bug,
  ExternalLink,
  Github,
  HardDrive,
  Heart,
  Info,
  LayoutDashboard,
  Lock,
  Map,
  MessageSquareText,
  MonitorSmartphone,
  Network,
  Package,
  PanelLeftClose,
  PanelLeftOpen,
  Router,
  Server,
  ServerCog,
  Settings,
  Shield,
  Sparkles,
  Wifi,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/ui/logo";
import { cn } from "@/lib/utils";
import { SITE_CONFIG } from "@/lib/site-config";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/routers", label: "Routers", icon: Router },
  { href: "/clients", label: "Clients", icon: MonitorSmartphone },
  { href: "/wireless", label: "Wireless", icon: Wifi },
  { href: "/network", label: "Network", icon: Network },
  { href: "/firewall", label: "Firewall", icon: Shield },
  { href: "/vpn", label: "VPN", icon: Lock },
  { href: "/monitoring", label: "Monitoring", icon: Activity },
  { href: "/dhcp", label: "DHCP", icon: Server },
  { href: "/packages", label: "Packages", icon: Package },
  { href: "/storage", label: "Storage", icon: HardDrive },
  { href: "/services", label: "Services", icon: ServerCog },
  { href: "/system", label: "System", icon: Settings },
  { href: "/chat", label: "AI Chat", icon: MessageSquareText },
  { href: "/settings", label: "Settings", icon: Settings },
];

type SecondaryItem = {
  label: string;
  href: string;
  icon: LucideIcon;
  external?: boolean;
};

const SECONDARY_ITEMS: SecondaryItem[] = [
  { label: "GitHub", href: SITE_CONFIG.repositoryUrl, icon: Github, external: true },
  { label: "Documentation", href: SITE_CONFIG.documentationUrl, icon: BookOpenText, external: true },
  { label: "Report Issue", href: SITE_CONFIG.issuesUrl, icon: Bug, external: true },
  { label: "Roadmap", href: SITE_CONFIG.roadmapUrl, icon: Map, external: true },
  { label: "Donate", href: "/support", icon: Heart },
  { label: "License", href: "/about#license", icon: Sparkles },
  { label: "About", href: "/about", icon: Info },
];

type SidebarProps = {
  collapsed: boolean;
  onToggle: () => void;
};

function isActive(pathname: string, href: string) {
  if (href === "/dashboard") {
    return pathname === href;
  }
  return pathname === href || pathname.startsWith(`${href}/`);
}

export function Sidebar({ collapsed, onToggle }: SidebarProps) {
  const pathname = usePathname();

  return (
    <aside
      className={cn(
        "flex h-full shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground transition-[width] duration-300",
        collapsed ? "w-16" : "w-60",
      )}
    >
      <div
        className={cn(
          "flex h-14 shrink-0 items-center border-b",
          collapsed ? "justify-center px-0" : "gap-2 px-4",
        )}
      >
        <Link
          href="/dashboard"
          className="flex items-center gap-2 overflow-hidden"
          aria-label={SITE_CONFIG.name}
        >
          <Logo
            withText={!collapsed}
            name={SITE_CONFIG.name}
            responsive
            ariaHiddenText
          />
        </Link>
      </div>

      <nav className="flex-1 space-y-1 overflow-y-auto p-2" aria-label="Primary">
        {NAV_ITEMS.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            title={collapsed ? item.label : undefined}
            aria-label={collapsed ? item.label : undefined}
            className={cn(
              "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              collapsed && "justify-center px-0",
              isActive(pathname, item.href)
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
            )}
          >
            <item.icon className="size-4 shrink-0" aria-hidden />
            {!collapsed ? <span className="truncate">{item.label}</span> : null}
          </Link>
        ))}
      </nav>

      <div className="px-2 pb-1" aria-hidden>
        <div className={cn("mx-auto h-px bg-border", collapsed ? "w-8" : "w-full")} />
      </div>

      <nav
        className="shrink-0 space-y-1 overflow-y-auto p-2"
        aria-label="Resources"
      >
        {SECONDARY_ITEMS.map((item) => {
          const className = cn(
            "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-sidebar-foreground/70 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
            collapsed && "justify-center px-0",
          );
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
          return item.external ? (
            <a
              key={item.label}
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
              key={item.label}
              href={item.href}
              className={className}
              title={collapsed ? item.label : undefined}
              aria-label={item.label}
            >
              {content}
            </Link>
          );
        })}
      </nav>

      <div className="border-t p-2">
        <button
          type="button"
          onClick={onToggle}
          className={cn(
            "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-sidebar-accent-foreground",
            collapsed && "justify-center px-0",
          )}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? (
            <PanelLeftOpen className="size-4 shrink-0" aria-hidden />
          ) : (
            <PanelLeftClose className="size-4 shrink-0" aria-hidden />
          )}
          {!collapsed ? <span>Collapse</span> : null}
        </button>
      </div>

      <div
        className={cn(
          "flex shrink-0 items-center border-t",
          collapsed ? "justify-center p-1.5" : "px-3 py-2",
        )}
      >
        <span
          className={cn(
            "inline-flex items-center rounded-full border bg-sidebar-accent/60 px-2 py-0.5 font-mono text-xs text-sidebar-foreground/80",
            collapsed && "px-1.5",
          )}
          title={`Version ${SITE_CONFIG.version}`}
        >
          v{SITE_CONFIG.version}
        </span>
      </div>
    </aside>
  );
}
