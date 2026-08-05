"use client";

import {
  Activity,
  LayoutDashboard,
  Lock,
  MessageSquareText,
  MonitorSmartphone,
  Network,
  PanelLeftClose,
  PanelLeftOpen,
  Router,
  Settings,
  Shield,
  Wifi,
  type LucideIcon,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { Logo } from "@/components/ui/logo";
import { SidebarOpenSource } from "@/components/layout/sidebar-open-source";
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
  { href: "/chat", label: "AI Chat", icon: MessageSquareText },
  { href: "/settings", label: "Settings", icon: Settings },
];

type SidebarProps = {
  collapsed: boolean;
  onToggle: () => void;
};

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

      <nav className="flex-1 space-y-1 overflow-y-auto p-2">
        {NAV_ITEMS.map((item) => {
          const active =
            item.href === "/dashboard"
              ? pathname === item.href
              : pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              aria-label={collapsed ? item.label : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                collapsed && "justify-center px-0",
                active
                  ? "bg-sidebar-accent text-sidebar-accent-foreground"
                  : "text-sidebar-foreground/80 hover:bg-sidebar-accent/60 hover:text-sidebar-accent-foreground",
              )}
            >
              <item.icon className="size-4 shrink-0" aria-hidden />
              {!collapsed ? <span className="truncate">{item.label}</span> : null}
            </Link>
          );
        })}
      </nav>

      <SidebarOpenSource collapsed={collapsed} />

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
    </aside>
  );
}
