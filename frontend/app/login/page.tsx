import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = {
  title: "Sign in",
};

/**
 * Operator sign-in. The browser login credentials (username + password) are
 * configured server-side; entering them here opens a scoped, short-lived
 * browser session. No credentials or master keys are ever stored in the
 * browser.
 */
export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6">
      <LoginForm />
    </main>
  );
}