import type { ReactNode } from "react";

import { AuthBoundary } from "@/components/auth/auth-boundary";
import { ThemeProvider } from "@/components/theme/theme-provider";

/**
 * Root layout: wraps every page in the client-side authentication boundary.
 * The boundary restores/validates the browser session and protects all routes
 * except /login, so no page ever renders unauthenticated router data.
 */
export default function RootLayoutWrapper({
  children,
}: Readonly<{ children: ReactNode }>) {
  return (
    <ThemeProvider>
      <AuthBoundary>{children}</AuthBoundary>
    </ThemeProvider>
  );
}