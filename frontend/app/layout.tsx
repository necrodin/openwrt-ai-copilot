import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

import { ThemeProvider } from "@/components/theme/theme-provider";
import { SITE_CONFIG } from "@/lib/site-config";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_CONFIG.appUrl),
  title: {
    default: SITE_CONFIG.name,
    template: `%s · ${SITE_CONFIG.name}`,
  },
  description: SITE_CONFIG.description,
  applicationName: SITE_CONFIG.name,
  authors: [{ name: SITE_CONFIG.author }],
  keywords: [
    "OpenWrt",
    "router",
    "AI",
    "copilot",
    "telemetry",
    "network",
    "LLM",
  ],
  icons: {
    icon: "/favicon.svg",
    apple: "/app-icon.svg",
  },
  manifest: "/manifest.webmanifest",
  openGraph: {
    title: SITE_CONFIG.name,
    description: SITE_CONFIG.tagline,
    type: "website",
    siteName: SITE_CONFIG.name,
    images: [
      {
        url: "/logo.svg",
        width: 64,
        height: 64,
        alt: SITE_CONFIG.name,
      },
    ],
  },
  twitter: {
    card: "summary",
    title: SITE_CONFIG.name,
    description: SITE_CONFIG.tagline,
    images: ["/logo.svg"],
  },
};

const THEME_INIT_SCRIPT = `
try {
  var t = localStorage.getItem("theme");
  if (t === "dark" || (t !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches)) {
    document.documentElement.classList.add("dark");
  }
} catch (e) {}
`;

export default function RootLayout({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen">
        <script dangerouslySetInnerHTML={{ __html: THEME_INIT_SCRIPT }} />
        <ThemeProvider>{children}</ThemeProvider>
      </body>
    </html>
  );
}
