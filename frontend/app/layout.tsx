import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";

import { ThemeProvider } from "@/components/theme/theme-provider";

export const metadata: Metadata = {
  title: "OpenWrt AI Copilot",
  description:
    "Provider-independent AI copilot for managing OpenWrt router fleets.",
  icons: {
    icon: "/favicon.svg",
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
