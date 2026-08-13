"use client";

import {
  Bot,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  MessageSquareText,
  Plus,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";

import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { StatusBadge } from "@/components/ui/status-badge";
import { useChat } from "@/hooks/use-chat";
import { authHeaders } from "@/lib/auth";
import { cn } from "@/lib/utils";

interface RouterSystem {
  hostname?: string | null;
  model?: string | null;
  board?: string | null;
  firmware?: string | null;
  kernel?: string | null;
  architecture?: string | null;
}

interface RouterCpu {
  usage_percent?: number | null;
  cores?: number | null;
}

interface RouterMemory {
  total_kb?: number | null;
  used_kb?: number | null;
  used_percent?: number | null;
}

interface RouterStorage {
  mountpoint?: string | null;
  filesystem?: string | null;
  total_gb?: number | null;
  used_gb?: number | null;
  use_percent?: number | null;
}

interface RouterSnapshotData {
  system: RouterSystem | null;
  cpu: RouterCpu | null;
  memory: RouterMemory | null;
  storage: RouterStorage[] | null;
}

interface RouterFinding {
  severity: string;
  title: string;
  description: string;
  recommendation: string;
}

interface RouterRecommendation {
  id: string;
  priority: string;
  title: string;
  description: string;
  action: string;
  impact: string;
}

interface RouterStatusResponse {
  snapshot: RouterSnapshotData | null;
  diagnosis: RouterFinding[];
  recommendations: RouterRecommendation[];
}

function formatKb(kb: number | null | undefined): string {
  if (kb == null) return "unknown";
  if (kb >= 1024 * 1024) return `${(kb / (1024 * 1024)).toFixed(1)} GB`;
  if (kb >= 1024) return `${(kb / 1024).toFixed(1)} MB`;
  return `${kb} KB`;
}

function findingVariant(severity: string): "default" | "secondary" | "destructive" | "outline" {
  if (severity === "critical") return "destructive";
  if (severity === "warning") return "outline";
  return "secondary";
}

function priorityVariant(priority: string): "default" | "secondary" | "destructive" | "outline" {
  if (priority === "urgent") return "destructive";
  if (priority === "high") return "outline";
  if (priority === "medium") return "secondary";
  return "default";
}

function RouterStatusCard({ data }: { data: RouterStatusResponse }) {
  const [collapsed, setCollapsed] = useState(false);
  const { snapshot, diagnosis, recommendations } = data;

  const toggle = () => setCollapsed((value) => !value);
  const chevron = collapsed ? (
    <ChevronRight className="size-4" aria-hidden />
  ) : (
    <ChevronDown className="size-4" aria-hidden />
  );

  return (
    <section className="rounded-xl border p-3">
      <div className="flex items-center justify-between gap-2">
        <button
          type="button"
          onClick={toggle}
          className="flex items-center gap-1 text-sm font-semibold tracking-tight hover:text-foreground"
          aria-expanded={!collapsed}
        >
          {chevron}
          Router Status
        </button>
        {snapshot === null ? (
          <Badge variant="destructive">Offline</Badge>
        ) : (
          <Badge variant="default">Online</Badge>
        )}
      </div>

      {!collapsed ? (
        <div className="mt-2 space-y-3">
          {snapshot === null ? (
            <p className="text-sm text-muted-foreground">Router unavailable</p>
          ) : (
            <>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Hostname</dt>
                  <dd className="font-medium">{snapshot.system?.hostname ?? "unknown"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Firmware</dt>
                  <dd className="font-medium">{snapshot.system?.firmware ?? "unknown"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Kernel</dt>
                  <dd className="font-medium">{snapshot.system?.kernel ?? "unknown"}</dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">CPU</dt>
                  <dd className="font-medium">
                    {snapshot.cpu?.usage_percent != null
                      ? `${snapshot.cpu.usage_percent.toFixed(1)}%`
                      : "N/A"}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Memory</dt>
                  <dd className="font-medium">
                    {snapshot.memory?.used_percent != null
                      ? `${snapshot.memory.used_percent.toFixed(1)}%`
                      : "N/A"}
                    {snapshot.memory?.total_kb != null
                      ? ` · ${formatKb(snapshot.memory.total_kb)}`
                      : ""}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Storage</dt>
                  <dd className="font-medium">
                    {snapshot.storage && snapshot.storage.length > 0
                      ? `${Math.max(
                          ...snapshot.storage.map((mount) => mount.use_percent ?? 0),
                        ).toFixed(1)}%`
                      : "N/A"}
                  </dd>
                </div>
              </dl>

              {diagnosis.length > 0 ? (
                <div className="space-y-1">
                  <h3 className="text-xs font-medium text-muted-foreground">Diagnosis</h3>
                  <ul className="space-y-2 text-sm">
                    {diagnosis.map((finding, index) => (
                      <li key={index} className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <Badge variant={findingVariant(finding.severity)}>
                            {finding.severity}
                          </Badge>
                          <span className="font-medium">{finding.title}</span>
                        </div>
                        <p className="text-muted-foreground">{finding.description}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {recommendations.length > 0 ? (
                <div className="space-y-1">
                  <h3 className="text-xs font-medium text-muted-foreground">Recommendations</h3>
                  <ul className="space-y-2 text-sm">
                    {recommendations.map((recommendation) => (
                      <li key={recommendation.id} className="space-y-0.5">
                        <div className="flex items-center gap-2">
                          <Badge variant={priorityVariant(recommendation.priority)}>
                            {recommendation.priority}
                          </Badge>
                          <span className="font-medium">{recommendation.title}</span>
                        </div>
                        <p className="text-muted-foreground">{recommendation.description}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}

/**
 * The real AI Copilot, rendered as a persistent right-hand panel in the console
 * shell. Always mounted so chat/session state survives navigation; the shell
 * controls expansion (expanded on the dashboard, collapsed elsewhere) and this
 * component only exposes expand/collapse — never a close button.
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

  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [routerLoading, setRouterLoading] = useState(true);
  const [routerError, setRouterError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/v1/router/status", { headers: authHeaders() })
      .then((response) => {
        if (!response.ok) {
          throw new Error(`Router status request failed (${response.status})`);
        }
        return response.json() as Promise<RouterStatusResponse>;
      })
      .then((data) => {
        if (!cancelled) {
          setRouterStatus(data);
          setRouterError(null);
        }
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setRouterError(err instanceof Error ? err.message : "Failed to load router status");
        }
      })
      .finally(() => {
        if (!cancelled) setRouterLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

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
    <aside className="fixed inset-y-0 right-0 z-40 flex w-80 flex-col border-l bg-background shadow-2xl lg:static lg:z-auto lg:w-80 lg:shadow-none">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b px-3 py-2.5">
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
            onClick={chat.startNewSession}
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
      </header>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-3">
        {routerLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : routerError ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-xs text-destructive">
            Router unavailable — {routerError}
          </p>
        ) : routerStatus ? (
          <RouterStatusCard data={routerStatus} />
        ) : null}

        {showSessions ? (
          <section className="space-y-1 rounded-xl border p-3">
            <div className="flex items-center justify-between">
              <h3 className="text-xs font-semibold text-muted-foreground">Sessions</h3>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-6 px-2 text-xs"
                onClick={chat.startNewSession}
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
                        {active
                          ? "Current chat"
                          : `Chat · ${session.message_count} msg`}
                      </button>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>
        ) : null}

        <div
          ref={scrollRef}
          className="flex max-h-[50vh] flex-col gap-3 overflow-y-auto"
        >
          {chat.messages.length === 0 ? (
            <div className="space-y-2 p-2 text-center">
              <MessageSquareText className="mx-auto size-8 text-muted-foreground/60" aria-hidden />
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
          onSend={(message) => void chat.sendMessage(message, null, null)}
          onStop={chat.stopStreaming}
          streaming={streaming}
          disabled={chat.status === "error"}
        />
        <p className="mt-2 text-center text-[10px] text-muted-foreground">
          Read-only · grounded in the router snapshot
        </p>
      </footer>
    </aside>
  );
}
