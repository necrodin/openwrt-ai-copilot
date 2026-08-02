"use client";

import { useEffect, useRef } from "react";
import { Activity, MessageSquareText } from "lucide-react";
import Link from "next/link";

import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { SessionSidebar } from "@/components/chat/session-sidebar";
import { Badge } from "@/components/ui/badge";
import { useChat } from "@/hooks/use-chat";

export default function ChatPage() {
  const {
    sessions,
    activeSessionId,
    messages,
    status,
    error,
    sendMessage,
    selectSession,
    startNewSession,
    stopStreaming,
  } = useChat();

  const scrollRef = useRef<HTMLDivElement | null>(null);
  const streaming = status === "streaming";

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [messages]);

  return (
    <main className="flex h-[100dvh] flex-col overflow-hidden">
      <header className="flex items-center justify-between gap-4 border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <MessageSquareText className="size-5" aria-hidden />
          <div>
            <h1 className="text-base font-semibold tracking-tight">
              AI Copilot
            </h1>
            <p className="text-xs text-muted-foreground">
              Answers from your router state · never invents data
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="outline" className="gap-1">
            <Activity className="size-3" aria-hidden />
            {streaming ? "Streaming" : "Ready"}
          </Badge>
          <Link
            href="/"
            className="underline underline-offset-4 hover:text-foreground"
          >
            Home
          </Link>
          <span aria-hidden>·</span>
          <Link
            href="/dashboard"
            className="underline underline-offset-4 hover:text-foreground"
          >
            Dashboard
          </Link>
        </div>
      </header>

      <div className="flex min-h-0 flex-1 flex-col md:flex-row">
        <SessionSidebar
          sessions={sessions}
          activeSessionId={activeSessionId}
          onSelect={(id) => void selectSession(id)}
          onNew={startNewSession}
        />

        <section className="flex min-h-0 flex-1 flex-col">
          <div
            ref={scrollRef}
            className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto px-4 py-4"
          >
            {messages.length === 0 ? (
              <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
                <MessageSquareText className="size-10 text-muted-foreground/60" aria-hidden />
                <div className="space-y-1">
                  <p className="text-base font-medium">Ask about your network</p>
                  <p className="max-w-md text-sm text-muted-foreground">
                    Questions are answered from this router&apos;s live state.
                    General networking explanations are labeled as such and
                    router facts are never invented.
                  </p>
                </div>
              </div>
            ) : (
              messages.map((turn, index) => (
                <MessageBubble
                  key={`${turn.role}-${index}-${turn.created_at ?? ""}`}
                  role={turn.role === "user" ? "user" : "assistant"}
                  content={turn.content}
                  provider={turn.provider}
                  model={turn.model}
                  streaming={turn.streaming}
                />
              ))
            )}
            {error ? (
              <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
                {error}
              </p>
            ) : null}
          </div>

          <footer className="border-t p-4">
            <ChatInput
              onSend={(message) =>
                void sendMessage(message, null, null)
              }
              onStop={stopStreaming}
              streaming={streaming}
              disabled={status === "error"}
            />
            <p className="mt-2 text-center text-[11px] text-muted-foreground">
              The assistant is read-only and grounded in the router snapshot. No
              RAG retrieval is active yet.
            </p>
          </footer>
        </section>
      </div>
    </main>
  );
}
