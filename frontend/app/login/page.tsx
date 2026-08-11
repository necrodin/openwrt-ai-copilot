import type { Metadata } from "next";

import { LoginForm } from "@/components/auth/login-form";

export const metadata: Metadata = {
  title: "Sign in",
};

/**
 * Operator sign-in. Authenticates against the stored application-user account
 * created by the first-run setup wizard (the /setup page shows in its place on
 * a fresh installation). Entering the credentials here opens a scoped,
 * short-lived browser session. No credentials or master keys are ever stored
 * in the browser, and the password never leaves the form except to the
 * backend, which hashes it with bcrypt.
 */
export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6">
      <LoginForm />
    </main>
  );
}