"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

/**
 * The AI Copilot is now a persistent panel inside the console shell
 * (expanded on the dashboard, collapsible everywhere). This route redirects to
 * the dashboard so any bookmarked/old links keep working without a second
 * Copilot implementation.
 */
export default function ChatPage() {
  const router = useRouter();

  useEffect(() => {
    router.replace("/dashboard");
  }, [router]);

  return null;
}
