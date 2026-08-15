"use client";

import {
  Bot,
  ChevronLeft,
  MessageSquareText,
  Plus,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { useChat } from "@/hooks/use-chat";
import { chatSelection, listProviders, selectableProviders, type ProviderSummary } from "@/lib/providers";
import { cn } from "@/lib/utils";

const providerSelectClasses =
  "h-7 min-w-0 flex-1 rounded-md border bg-background px-2 text-xs text-foreground shadow-xs";

/**
 * The real AI Copilot — a conversation-only panel, rendered as a native child
 * of the console's main content. Always mounted so chat/session state survives
 * navigation; the shell controls expansion (expanded on the dashboard,
 * collapsed elsewhere). Exposes only expand/collapse — never a close button.
 *
 * Router status, diagnosis and recommendations live on the Dashboard; they are
 * deliberately not duplicated here.
 */
export function CopilotPanel({
  expanded,
  onToggle,
}: {
  expanded: boolean;
  onToggle: () => void;
}) {
  const chat = useChat();
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const streaming = chat.status === "streaming";
  const [showSessions, setShowSessions] = useState(false);

  const [providerOptions, setProviderOptions] = useState<ProviderSummary[]>([]);
  const [selectedProvider, setSelectedProvider] = useState<string | null>(null);
  const [defaultProvider, setDefaultProviderSummary] = useState<ProviderSummary | null>(null);

  // Model picker state: "provider" uses the selected provider's configured
  // model; "custom" lets the operator type any model for the next message.
  // Switching provider resets back to the provider's configured model.
  const [modelMode, setModelMode] = useState<"provider" | "custom">("provider");
  const [customModel, setCustomModel] = useState("");

  const resetModelSelection = () => {
    setModelMode("provider");
    setCustomModel("");
  };

  const selectProvider = (type: string | null) => {
    setSelectedProvider(type);
    resetModelSelection();
  };

  // Load enabled providers once so the selector never hardcodes provider
  // names. Best-effort: if the list cannot be fetched the Copilot keeps
  // working through the backend default and the selector simply stays hidden.
  useEffect(() => {
    let cancelled = false;
    listProviders()
      .then((list) => {
        if (cancelled) {
          return;
        }
        const selectable = selectableProviders(list.providers);
        setProviderOptions(selectable);
        const fallback =
          selectable.find((provider) => provider.type === list.default_provider) ?? null;
        setDefaultProviderSummary(fallback);
        setSelectedProvider(fallback ? fallback.type : null);
      })
      .catch(() => {
        // Best-effort: keep the panel usable with the backend default.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Selection for the NEXT chat request only: the configured model of the
  // chosen provider (or a manual override), or the backend default when
  // nothing is selected.
  const selection = chatSelection(
    providerOptions,
    selectedProvider,
    modelMode === "custom" ? customModel : "",
  );

  // The selected provider's configured model (what "provider mode" sends).
  const configuredModel =
    providerOptions.find((provider) => provider.type === selectedProvider)?.model || null;

  const startNewChat = () => {
    chat.startNewSession();
    // A fresh conversation starts from the configured global default; the
    // global default itself is never changed by the in-chat selector.
    selectProvider(defaultProvider ? defaultProvider.type : null);
  };

  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [chat.messages]);

  if (!expanded) {
    return (
      <button
        type="button"
        onClick={onToggle}
        aria-label="Expand AI Copilot"
        title="AI Copilot"
        className="flex w-10 shrink-0 items-center justify-center border-l bg-card/40 text-muted-foreground transition-colors hover:text-foreground"
      >
        <Bot className="size-4" aria-hidden />
      </button>
    );
  }

  return (
    <div className="fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l bg-background shadow-2xl lg:static lg:z-auto lg:w-80 lg:shadow-none">
      <header className="flex shrink-0 flex-col border-b">
        <div className="flex shrink-0 items-center justify-between gap-2 px-3 py-2.5">
          <div className="flex min-w-0 items-center gap-2">
            <Bot className="size-4 shrink-0 text-primary" aria-hidden />
            <h2 className="truncate text-sm font-semibold">AI Copilot</h2>
          </div>
          <div className="flex shrink-0 items-center gap-1">
            <StatusBadge
              label={streaming ? "Streaming" : "Ready"}
              tone={streaming ? "info" : "neutral"}
              dot={false}
            />
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-7"
              onClick={() => setShowSessions((value) => !value)}
              aria-label="Toggle sessions"
              title="Chat sessions"
            >
              <MessageSquareText className="size-4" aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-7"
              onClick={startNewChat}
              aria-label="New chat"
              title="New chat"
            >
              <Plus className="size-4" aria-hidden />
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-7"
              onClick={onToggle}
              aria-label="Collapse AI Copilot"
              title="Collapse AI Copilot"
            >
              <ChevronLeft className="size-4" aria-hidden />
            </Button>
          </div>
        </div>

        {providerOptions.length > 0 ? (
          <div className="flex items-center gap-1.5 border-t px-3 py-1.5">
            <select
              aria-label="AI provider"
              title="AI provider used for the next message"
              className={providerSelectClasses}
              value={selectedProvider ?? ""}
              onChange={(event) => selectProvider(event.target.value || null)}
              disabled={streaming}
            >
              {selectedProvider === null ? (
                <option value="">Select provider…</option>
              ) : null}
              {providerOptions.map((provider) => (
                <option key={provider.type} value={provider.type}>
                  {provider.name || provider.type}
                </option>
              ))}
            </select>
            <select
              aria-label="Model"
              title="Model used for the next message"
              className={providerSelectClasses}
              value={modelMode === "custom" ? "__custom__" : "__configured__"}
              onChange={(event) => {
                if (event.target.value === "__custom__") {
                  setModelMode("custom");
                } else {
                  setModelMode("provider");
                }
              }}
              disabled={streaming}
            >
              <option value="__configured__">
                {configuredModel ?? "Default model"}
              </option>
              <option value="__custom__">Custom model…</option>
            </select>
            {modelMode === "custom" ? (
              <input
                aria-label="Custom model"
                title="Type any model for the next message"
                className={providerSelectClasses}
                value={customModel}
                onChange={(event) => setCustomModel(event.target.value)}
                placeholder="e.g. gpt-4o-mini"
                disabled={streaming}
              />
            ) : null}
          </div>
        ) : null}
      </header>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto p-3">
        {showSessions ? (
          <section className="space-y-1 rounded-xl border p-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-muted-foreground">Sessions</h3>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={startNewChat}
              >
                <Plus className="size-3" aria-hidden />
                New
              </Button>
            </div>
            {chat.sessions.length === 0 ? (
              <p className="text-xs text-muted-foreground">No conversations yet.</p>
            ) : (
              <ul className="max-h-40 space-y-1 overflow-y-auto">
                {chat.sessions.map((session) => {
                  const active = session.session_id === chat.activeSessionId;
                  return (
                    <li key={session.session_id}>
                      <button
                        type="button"
                        onClick={() => void chat.selectSession(session.session_id)}
                        className={cn(
                          "w-full rounded-md px-2 py-1.5 text-left text-xs transition-colors",
                          active
                            ? "bg-accent text-accent-foreground"
                            : "text-muted-foreground hover:bg-accent/60 hover:text-accent-foreground",
                        )}
                      >
                        {active ? "Current chat" : `Chat · ${session.message_count} msg`}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        ) : null}

        <div ref={scrollRef} className="flex flex-1 flex-col gap-3 overflow-y-auto">
          {chat.messages.length === 0 ? (
            <div className="flex flex-1 flex-col items-center justify-center gap-2 p-4 text-center">
              <MessageSquareText className="size-8 text-muted-foreground/60" aria-hidden />
              <p className="text-sm font-medium">Ask about your network</p>
              <p className="text-xs text-muted-foreground">
                Questions are answered from this router&apos;s live state. Router
                facts are never invented.
              </p>
            </div>
          ) : (
            chat.messages.map((turn, index) => (
              <MessageBubble
                key={`${turn.role}-${index}-${turn.created_at ?? ""}`}
                role={turn.role === "user" ? "user" : "assistant"}
                content={turn.content}
                provider={turn.provider}
                model={turn.model}
                streaming={turn.streaming}
                routerContext={turn.router_context}
              />
            ))
          )}
          {chat.error ? (
            <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
              {chat.error}
            </p>
          ) : null}
        </div>
      </div>

      <footer className="shrink-0 border-t p-3">
        <ChatInput
          onSend={(message) => void chat.sendMessage(message, selection.provider, selection.model)}
          onStop={chat.stopStreaming}
          streaming={streaming}
          disabled={chat.status === "error"}
        />
        <p className="mt-2 text-center text-[10px] text-muted-foreground">
          Read-only · grounded in the router snapshot
        </p>
      </footer>
    </div>
  );
}
