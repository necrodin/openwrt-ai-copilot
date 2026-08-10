import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = {
  title: "Sign in",
};

/**
 * Operator sign-in. The backend operator API keys are configured server-side;
 * the operator enters one here and the backend exchanges it for a scoped,
 * short-lived session token. No master key is ever stored in the browser.
 */
export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6">
      <LoginForm />
    </main>
  );
}