import {
  Activity,
  BookOpenText,
  Cog,
  Github,
  Globe,
  HardDrive,
  LayoutDashboard,
  Lock,
  Map,
  MonitorSmartphone,
  Network,
  Package,
  Server,
  ServerCog,
  Settings,
  Shield,
  Wifi,
  type LucideIcon,
} from "lucide-react";

import { SITE_CONFIG } from "@/lib/site-config";

export type NavItem = {
  href: string;
  label: string;
  icon: LucideIcon;
};

/** Primary operational navigation (top nav). */
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { href: "/clients", label: "Clients", icon: MonitorSmartphone },
  { href: "/wireless", label: "Wireless", icon: Wifi },
  { href: "/network", label: "Network", icon: Network },
  { href: "/firewall", label: "Firewall", icon: Shield },
  { href: "/vpn", label: "VPN", icon: Lock },
  { href: "/monitoring", label: "Monitoring", icon: Activity },
  { href: "/dhcp", label: "DHCP", icon: Server },
  { href: "/dns", label: "DNS", icon: Globe },
  { href: "/packages", label: "Packages", icon: Package },
  { href: "/storage", label: "Storage", icon: HardDrive },
  { href: "/services", label: "Services", icon: ServerCog },
  { href: "/system", label: "System", icon: Cog },
  { href: "/settings", label: "Settings", icon: Settings },
];

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
