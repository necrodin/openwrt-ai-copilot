"use client";

import { Plus, MessageSquare } from "lucide-react";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { ChatSessionSummary } from "@/lib/chat";

type SessionSidebarProps = {
  sessions: ChatSessionSummary[];
  activeSessionId: string | null;
  onSelect: (sessionId: string) => void;
  onNew: () => void;
};

function formatUpdatedAt(iso: string | null): string {
  if (!iso) {
    return "just now";
  }
  const date = new Date(iso);
  const now = Date.now();
  const diffMs = now - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) {
    return "just now";
  }
  if (minutes < 60) {
    return `${minutes}m ago`;
  }
  const hours = Math.floor(minutes / 60);
  if (hours < 24) {
    return `${hours}h ago`;
  }
  const days = Math.floor(hours / 24);
  if (days < 7) {
    return `${days}d ago`;
  }
  return date.toLocaleDateString();
}

export function SessionSidebar({
  sessions,
  activeSessionId,
  onSelect,
  onNew,
}: SessionSidebarProps) {
  return (
    <aside className="flex w-full flex-col gap-3 border-r bg-muted/30 p-3 md:w-64 md:min-h-full">
      <Button onClick={onNew} className="w-full justify-start" variant="secondary">
        <Plus className="size-4" aria-hidden />
        New chat
      </Button>

      <div className="flex min-h-0 flex-1 flex-col gap-1 overflow-y-auto">
        {sessions.length === 0 ? (
          <p className="px-2 py-3 text-xs text-muted-foreground">
            No conversations yet. Ask a question to get started.
          </p>
        ) : (
          sessions.map((session) => {
            const active = session.session_id === activeSessionId;
            return (
              <button
                key={session.session_id}
                onClick={() => onSelect(session.session_id)}
                className={cn(
                  "flex items-start gap-2 rounded-md px-2 py-2 text-left text-sm transition-colors",
                  active
                    ? "bg-accent text-accent-foreground"
                    : "hover:bg-accent/60 hover:text-accent-foreground",
                )}
              >
                <MessageSquare className="mt-0.5 size-3.5 shrink-0" aria-hidden />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="truncate">
                    {session.session_id === activeSessionId
                      ? "Current chat"
                      : `Chat ${session.message_count} msgs`}
                  </span>
                  <span className="text-[11px] text-muted-foreground">
                    {formatUpdatedAt(session.updated_at)}
                  </span>
                </span>
              </button>
            );
          })
        )}
      </div>
    </aside>
  );
}
