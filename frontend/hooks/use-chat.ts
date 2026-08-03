"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  fetchChatHistory,
  fetchChatSessions,
  newSessionId,
  streamChatMessage,
  type ChatSessionSummary,
  type ChatTurn,
} from "@/lib/chat";

export type ChatStatus = "idle" | "streaming" | "error";

/**
 * Chat session state: message list for the active session, session sidebar,
 * and SSE streaming via the backend chat endpoint.
 */
export function useChat() {
  const [sessions, setSessions] = useState<ChatSessionSummary[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatTurn[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);

  const abortRef = useRef<AbortController | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      abortRef.current?.abort();
    };
  }, []);

  const refreshSessions = useCallback(async () => {
    try {
      const list = await fetchChatSessions();
      if (mountedRef.current) {
        setSessions(list);
      }
    } catch {
      // sidebar refresh is best-effort
    }
  }, []);

  const stopStreaming = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const selectSession = useCallback(
    async (sessionId: string) => {
      stopStreaming();
      setActiveSessionId(sessionId);
      setStatus("idle");
      setError(null);
      try {
        const turns = await fetchChatHistory(sessionId);
        if (mountedRef.current) {
          setMessages(turns);
        }
      } catch {
        if (mountedRef.current) {
          setError("Could not load chat history.");
        }
      }
    },
    [stopStreaming],
  );

  const startNewSession = useCallback(() => {
    stopStreaming();
    setActiveSessionId(null);
    setMessages([]);
    setStatus("idle");
    setError(null);
  }, [stopStreaming]);

  const sendMessage = useCallback(
    async (content: string, provider: string | null, model: string | null) => {
      const trimmed = content.trim();
      if (!trimmed || status === "streaming") {
        return;
      }
      stopStreaming();

      const sessionId = activeSessionId ?? newSessionId();
      setActiveSessionId(sessionId);
      setError(null);

      const userTurn: ChatTurn = {
        role: "user",
        content: trimmed,
        created_at: new Date().toISOString(),
        provider: null,
        model: null,
      };
      const assistantTurn: ChatTurn = {
        role: "assistant",
        content: "",
        created_at: new Date().toISOString(),
        provider: null,
        model: null,
        streaming: true,
        router_context: null,
      };
      setMessages((prev) => [...prev, userTurn, assistantTurn]);
      setStatus("streaming");

      const controller = new AbortController();
      abortRef.current = controller;

      await streamChatMessage(
        { session_id: sessionId, message: trimmed, provider, model },
        {
          signal: controller.signal,
          onDelta: (delta) => {
            setMessages((prev) => {
              const next = [...prev];
              const current = next[next.length - 1];
              if (current?.role === "assistant") {
                next[next.length - 1] = {
                  ...current,
                  content: current.content + delta,
                };
              }
              return next;
            });
          },
          onDone: (event) => {
            setMessages((prev) => {
              const next = [...prev];
              const current = next[next.length - 1];
              if (current?.role === "assistant") {
                next[next.length - 1] = {
                  ...current,
                  content: event.reply || current.content,
                  provider: event.provider,
                  model: event.model,
                  streaming: false,
                  router_context: event.router_context ?? null,
                };
              }
              return next;
            });
            setStatus("idle");
            void refreshSessions();
          },
          onError: (message) => {
            setMessages((prev) => {
              const next = [...prev];
              const current = next[next.length - 1];
              if (current?.role === "assistant") {
                next[next.length - 1] = {
                  ...current,
                  content: "",
                  streaming: false,
                };
              }
              return next;
            });
            setError(message);
            setStatus("idle");
          },
        },
      );
    },
    [activeSessionId, refreshSessions, status, stopStreaming],
  );

  useEffect(() => {
    if (loaded) {
      return;
    }
    setLoaded(true);
    void refreshSessions();
  }, [loaded, refreshSessions]);

  return {
    sessions,
    activeSessionId,
    messages,
    status,
    error,
    sendMessage,
    selectSession,
    startNewSession,
    stopStreaming,
    refreshSessions,
  };
}
