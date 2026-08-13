"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * Console entry point. The console is reached directly at /dashboard (login
 * and setup now land here), so the root route simply forwards there. Router
 * onboarding/management lives under Settings.
 */
export default function Home() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return null;
}
