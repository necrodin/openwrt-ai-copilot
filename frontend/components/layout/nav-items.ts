import {
  BookOpenText,
  Github,
  Map,
  type LucideIcon,
} from "lucide-react";

import { SITE_CONFIG } from "@/lib/site-config";

export type NavLinkItem = {
  label: string;
  href: string;
};

export type NavCategory =
  | { type: "link"; label: string; href: string }
  | { type: "dropdown"; label: string; items: NavLinkItem[] };

/**
 * Top-level navigation. Only the categories are visible in the top bar;
 * dropdown items open below their category.
 */
export const TOP_CATEGORIES: NavCategory[] = [
  { type: "link", label: "Dashboard", href: "/dashboard" },
  {
    type: "dropdown",
    label: "Network",
    items: [
      { label: "Clients", href: "/clients" },
      { label: "Wireless", href: "/wireless" },
      { label: "Network", href: "/network" },
      { label: "DHCP", href: "/dhcp" },
      { label: "DNS", href: "/dns" },
    ],
  },
  {
    type: "dropdown",
    label: "Security",
    items: [
      { label: "Firewall", href: "/firewall" },
      { label: "VPN", href: "/vpn" },
    ],
  },
  {
    type: "dropdown",
    label: "Monitoring",
    items: [
      { label: "Monitoring", href: "/monitoring" },
      { label: "Services", href: "/services" },
      { label: "System", href: "/system" },
    ],
  },
  {
    type: "dropdown",
    label: "Packages",
    items: [
      { label: "Packages", href: "/packages" },
      { label: "Storage", href: "/storage" },
    ],
  },
  { type: "link", label: "Settings", href: "/settings" },
];

/** Whether a route belongs to a category (for the active state). */
export function categoryActive(category: NavCategory, pathname: string): boolean {
  if (category.type === "link") {
    return category.href === "/dashboard"
      ? pathname === category.href
      : pathname === category.href || pathname.startsWith(`${category.href}/`);
  }
  return category.items.some(
    (item) => pathname === item.href || pathname.startsWith(`${item.href}/`),
  );
}

export type ExternalItem = {
  label: string;
  href: string;
  icon: LucideIcon;
};

/** External project links — icon-only with tooltips + accessible labels. */
export const EXTERNAL_ITEMS: ExternalItem[] = [
  { label: "GitHub", href: SITE_CONFIG.repositoryUrl, icon: Github },
  { label: "Documentation", href: SITE_CONFIG.documentationUrl, icon: BookOpenText },
  { label: "Roadmap", href: SITE_CONFIG.roadmapUrl, icon: Map },
];

/** Internal resource links — compact text, secondary to the operational menu. */
export const RESOURCE_ITEMS: { label: string; href: string }[] = [
  { label: "Donate", href: "/support" },
  { label: "License", href: "/about#license" },
  { label: "About", href: "/about" },
];
