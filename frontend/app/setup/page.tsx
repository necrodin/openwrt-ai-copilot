import type { Metadata } from "next";

import { SetupForm } from "@/components/auth/setup-form";

export const metadata: Metadata = {
  title: "Create your administrator account",
};

/**
 * First-run administrator setup. Shown instead of the login page only while
 * the backend has no application users; once the initial admin exists the
 * backend marks setup complete and the auth boundary sends visitors to the
 * normal sign-in page instead. No credentials or master keys are ever stored
 * in the browser.
 */
export default function SetupPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-6 bg-background p-6">
      <SetupForm />
    </main>
  );
}