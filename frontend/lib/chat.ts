import { API_BASE_URL } from "@/lib/api";

export type ChatRole = "user" | "assistant" | "system";

export type ChatTurn = {
  role: ChatRole;
  content: string;
  created_at: string | null;
  provider: string | null;
  model: string | null;
  streaming?: boolean;
  router_context?: string | null;
};

export type ChatSessionSummary = {
  session_id: string;
  updated_at: string | null;
  message_count: number;
};

export type ChatCompletionResponse = {
  session_id: string;
  reply: string;
  provider: string;
  model: string;
  usage: { prompt_tokens: number; completion_tokens: number } | null;
  router_context?: string | null;
};

export type ChatStreamEvent =
  | { type: "session"; session_id: string }
  | { type: "delta"; content: string }
  | {
      type: "done";
      reply: string;
      provider: string;
      model: string;
      router_context?: string | null;
    }
  | { type: "error"; message: string };

export type ChatStreamHandlers = {
  onDelta?: (delta: string) => void;
  onDone?: (event: ChatStreamEvent & { type: "done" }) => void;
  onError?: (message: string) => void;
  signal?: AbortSignal;
};

export type ChatRequestOptions = {
  session_id: string;
  message: string;
  provider?: string | null;
  model?: string | null;
};

async function jsonOrThrow(res: Response): Promise<unknown> {
  if (!res.ok) {
    let detail = `Request failed with status ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // non-JSON error body; keep the status-based message
    }
    throw new Error(detail);
  }
  return res.json();
}

/** POST a message and receive the full (non-streaming) reply. */
export async function sendChatMessage(
  options: ChatRequestOptions,
  signal?: AbortSignal,
): Promise<ChatCompletionResponse> {
  const res = await fetch(`${API_BASE_URL}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: options.session_id,
      message: options.message,
      provider: options.provider ?? null,
      model: options.model ?? null,
    }),
    signal,
  });
  return (await jsonOrThrow(res)) as ChatCompletionResponse;
}

/**
 * POST a message and consume the Server-Sent Events reply, invoking the
 * delta/done/error handlers as events arrive. Resolves once the stream ends.
 */
export async function streamChatMessage(
  options: ChatRequestOptions,
  handlers: ChatStreamHandlers = {},
): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      session_id: options.session_id,
      message: options.message,
      provider: options.provider ?? null,
      model: options.model ?? null,
    }),
    signal: handlers.signal,
  });

  if (!res.ok || !res.body) {
    let detail = `Stream request failed with status ${res.status}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body.detail) {
        detail = body.detail;
      }
    } catch {
      // keep the status-based message
    }
    handlers.onError?.(detail);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const events = buffer.split("\n\n");
      buffer = events.pop() ?? "";

      for (const raw of events) {
        const event = parseSseEvent(raw);
        if (event === null) {
          continue;
        }
        switch (event.type) {
          case "delta":
            handlers.onDelta?.(event.content);
            break;
          case "done":
            handlers.onDone?.(event);
            break;
          case "error":
            handlers.onError?.(event.message);
            break;
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

function parseSseEvent(raw: string): ChatStreamEvent | null {
  const data = raw
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice(5).trimStart())
    .join("\n");
  if (!data) {
    return null;
  }
  try {
    return JSON.parse(data) as ChatStreamEvent;
  } catch {
    return null;
  }
}

/** Fetch the persisted turns for a session, oldest first. */
export async function fetchChatHistory(
  sessionId: string,
  signal?: AbortSignal,
): Promise<ChatTurn[]> {
  const url = new URL(`${API_BASE_URL}/chat/history`, window.location.origin);
  url.searchParams.set("session_id", sessionId);
  const res = await fetch(url, { signal });
  const body = (await jsonOrThrow(res)) as {
    messages: Array<{
      role: ChatRole;
      content: string;
      created_at: string | null;
      provider: string | null;
      model: string | null;
    }>;
  };
  return body.messages;
}

/** Fetch the list of known chat sessions, newest first. */
export async function fetchChatSessions(
  signal?: AbortSignal,
): Promise<ChatSessionSummary[]> {
  const res = await fetch(`${API_BASE_URL}/chat/sessions`, { signal });
  const body = (await jsonOrThrow(res)) as { sessions: ChatSessionSummary[] };
  return body.sessions;
}

/** Generate a fresh client-side session id. */
export function newSessionId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `session-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
