"use client";

import { LogOut } from "lucide-react";

import { useAuth } from "@/components/auth/auth-boundary";
import { cn } from "@/lib/utils";

/**
 * Signs the operator out: revokes the session server-side and returns to the
 * login page. Shows the current role so read-only operators know write actions
 * are unavailable to them.
 */
export function LogoutButton({ className }: { className?: string }) {
  const { role, logout } = useAuth();

  return (
    <div className={cn("flex items-center gap-1", className)}>
      {role === "readonly" ? (
        <span
          className="hidden rounded-full border px-2 py-0.5 text-xs text-muted-foreground sm:inline"
          title="Read-only session: router changes are disabled"
        >
          Read-only
        </span>
      ) : null}
      <button
        type="button"
        onClick={() => void logout()}
        className="inline-flex items-center gap-2 rounded-md px-2 py-1.5 text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-accent-foreground"
        aria-label="Sign out"
        title="Sign out"
      >
        <LogOut className="size-4" aria-hidden />
        <span className="hidden sm:inline">Sign out</span>
      </button>
    </div>
  );
}