"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Activity, ChevronDown, ChevronRight, MessageSquareText } from "lucide-react";
import Link from "next/link";

import { ChatInput } from "@/components/chat/chat-input";
import { MessageBubble } from "@/components/chat/message-bubble";
import { SessionSidebar } from "@/components/chat/session-sidebar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useChat } from "@/hooks/use-chat";

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
        <div className="flex items-center gap-2">
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
        {snapshot === null ? (
          <p className="text-xs text-muted-foreground">Router unavailable</p>
        ) : null}
      </div>

      {!collapsed ? (
        <div className="mt-2 space-y-3">
          {snapshot === null ? (
            <p className="text-sm text-muted-foreground">Router unavailable</p>
          ) : (
            <>
              <dl className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2 xl:grid-cols-3">
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Hostname</dt>
                  <dd className="font-medium">
                    {snapshot.system?.hostname ?? "unknown"}
                  </dd>
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
                  <dt className="text-muted-foreground">CPU Usage</dt>
                  <dd className="font-medium">
                    {snapshot.cpu?.usage_percent != null
                      ? `${snapshot.cpu.usage_percent.toFixed(1)}%`
                      : "N/A"}
                    {snapshot.cpu?.cores != null ? ` · ${snapshot.cpu.cores} cores` : ""}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Memory Usage</dt>
                  <dd className="font-medium">
                    {snapshot.memory?.used_percent != null
                      ? `${snapshot.memory.used_percent.toFixed(1)}%`
                      : "N/A"}
                    {" · "}
                    {formatKb(snapshot.memory?.used_kb)} / {formatKb(snapshot.memory?.total_kb)}
                  </dd>
                </div>
                <div className="flex justify-between gap-2">
                  <dt className="text-muted-foreground">Storage Usage</dt>
                  <dd className="font-medium">
                    {snapshot.storage && snapshot.storage.length > 0
                      ? `${Math.max(
                          ...snapshot.storage.map((mount) => mount.use_percent ?? 0),
                        ).toFixed(1)}%`
                      : "N/A"}
                  </dd>
                </div>
              </dl>

              {snapshot.storage && snapshot.storage.length > 0 ? (
                <ul className="space-y-1 text-sm">
                  {snapshot.storage.map((mount) => (
                    <li
                      key={mount.mountpoint ?? mount.filesystem ?? "mount"}
                      className="flex justify-between gap-2"
                    >
                      <span className="text-muted-foreground">
                        {mount.mountpoint ?? "?"} ({mount.filesystem ?? "?"})
                      </span>
                      <span className="font-medium">
                        {mount.use_percent != null ? `${mount.use_percent.toFixed(1)}%` : "N/A"}
                        {" · "}
                        {mount.used_gb != null ? `${mount.used_gb.toFixed(1)}G` : "?"} /{" "}
                        {mount.total_gb != null ? `${mount.total_gb.toFixed(1)}G` : "?"}
                      </span>
                    </li>
                  ))}
                </ul>
              ) : null}

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
                        <p className="text-muted-foreground">
                          Recommendation: {finding.recommendation}
                        </p>
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
                        <p className="text-muted-foreground">
                          Action: {recommendation.action}
                        </p>
                        <p className="text-muted-foreground">
                          Impact: {recommendation.impact}
                        </p>
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

  const [routerStatus, setRouterStatus] = useState<RouterStatusResponse | null>(null);
  const [routerLoading, setRouterLoading] = useState(true);
  const [routerError, setRouterError] = useState<string | null>(null);

  const loadRouterStatus = useCallback(async () => {
    try {
      const response = await fetch("/api/v1/router/status");
      if (!response.ok) {
        throw new Error(`Router status request failed (${response.status})`);
      }
      const data: RouterStatusResponse = await response.json();
      setRouterStatus(data);
      setRouterError(null);
    } catch (err) {
      setRouterError(err instanceof Error ? err.message : "Failed to load router status");
    } finally {
      setRouterLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRouterStatus();
  }, [loadRouterStatus]);

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
          <div className="border-b px-4 py-3">
            {routerLoading ? (
              <Skeleton className="h-24 w-full rounded-xl" />
            ) : routerError ? (
              <section className="rounded-xl border border-destructive/40 bg-destructive/10 p-3">
                <h2 className="text-sm font-semibold tracking-tight">Router Status</h2>
                <p className="mt-1 text-sm text-destructive">
                  Router unavailable — {routerError}
                </p>
              </section>
            ) : routerStatus ? (
              <RouterStatusCard data={routerStatus} />
            ) : null}
          </div>

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
                  routerContext={turn.router_context}
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
              onSend={(message) => {
                void loadRouterStatus();
                void sendMessage(message, null, null);
              }}
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
