# Sprint 5 — AI Chat

Status: **complete** (verification: 135 pytest passed, ruff clean, Next.js
typecheck + lint + production build pass; full stack — mock OpenAI-compatible
provider → FastAPI → Next.js proxy → SSE stream — verified against a running
backend).

## Goal

A natural-language chat that answers questions about **this** router from its
live state and explains networking concepts — without ever inventing router
data. The chat talks to AI **only through the provider interface**
(`ProviderManager` → `ChatProvider.chat()/stream()`); no provider SDK and no
direct OpenAI/NVIDIA calls anywhere. No RAG is wired in yet.

## What the model sees

Every request is built by `app/services/chat_service.py` and carries a system
prompt plus the router's current state:

- The **router JSON** is the live `DeviceSnapshot` (CPU, memory, storage,
  network WAN/LAN, firewall, VPN, wireless, clients/ARP, routing, kernel…)
  collected by the Sprint-4 snapshot service and injected as read-only context.
- The system prompt **hard-constrains the model**: answer only from the
  provided router JSON, never invent/guess IPs, hostnames, services, versions,
  ports, temperatures, tunnel peers, or firewall rules; when data is absent,
  say so; general networking explanations are allowed but must be labeled as
  general knowledge; read-only, Markdown output, no emojis.
- When no router state is available the prompt says so explicitly and the model
  must refuse to fabricate values.

## API

| Endpoint | Behaviour |
|---|---|
| `POST /api/v1/chat` | Non-streaming reply; persists both turns. |
| `POST /api/v1/chat/stream` | Server-Sent Events stream (`session` → `delta`… → `done` / `error`). |
| `GET /api/v1/chat/history?session_id=` | Stored turns, oldest first. |
| `GET /api/v1/chat/sessions` | Session list (newest first) for the sidebar. |

- **Routing**: `ChatService.provider_for()` picks a chat-capable provider via
  `ProviderManager.get_for_capability(CAPABILITY_CHAT, preferred=…)`; no
  provider is ever instantiated directly. A missing chat provider returns 503
  (or an SSE `error` event on the stream path).
- **History**: turns are appended to SQLite via `app/db/chat_store.py`
  (append-only, grouped by `session_id`). The stored history is re-fed into the
  next request's context, capped at 50 records.
- **Failure semantics**: the user turn is recorded before the AI call, so an
  interrupted reply leaves the user's intent logged (the assistant turn is
  only stored when a reply is produced).

## Frontend (`/chat`)

- `app/chat/page.tsx` — page shell: header (status + nav), session sidebar,
  scrollable message list, composer footer.
- `hooks/use-chat.ts` — session/message state, SSE streaming with a live
  streaming cursor, stop/cancel via `AbortController`, error surfacing, sidebar
  refresh.
- `lib/chat.ts` — types + client: `streamChatMessage()` reads the SSE feed with
  a fetch `ReadableStream`/`TextDecoder` parser; `fetchChatHistory()`,
  `fetchChatSessions()`, `newSessionId()`.
- `components/chat/message-bubble.tsx` — user vs assistant bubbles; assistant
  replies render **Markdown** and carry a `provider · model` badge from the
  `done` event.
- `components/chat/markdown.tsx` — `react-markdown` + `remark-gfm` renderer:
  headings, lists, inline code, fenced code blocks, blockquotes, GFM tables,
  links (external). Raw HTML in model output is **not** rendered.
- `components/chat/chat-input.tsx` — auto-growing textarea, Enter to send,
  Shift+Enter for a newline, stop button while streaming.
- `components/chat/session-sidebar.tsx` — new-chat + session list with relative
  timestamps.
- Home and dashboard link to the chat; chat links back to both.

New npm dependencies: `react-markdown`, `remark-gfm`. No other frontend deps.

## No hallucination, concretely

1. Router facts must be **in the snapshot JSON** or the answer must say the
   data isn't available — enforced by the system prompt and verified by tests
   (`test_system_prompt_includes_router_state`, `test_system_prompt_without_router_data`).
2. The frontend never sends router state typed by the user; the snapshot is the
   only source of truth.
3. RAG is not enabled (`rag/` remains a stub), so there is no external
   retrieval to conflate with live router state.

## Tests

`tests/unit/test_chat_api.py` (mocked OpenAI-compatible transport — no network):

- System prompt embeds the router JSON + no-invention/read-only rules, and the
  no-data variant.
- Non-streaming chat routes through the provider interface and records history.
- History persists, feeds the next turn's context, and lists sessions.
- SSE stream yields deltas, persists the assembled reply, and emits error
  events when no provider is configured.
- No-provider non-stream returns 503.

`make test` runs 135 tests; `make lint` is clean.

## Run

```bash
# configure a chat-capable provider (see providers.example.yaml)
cp providers.example.yaml providers.yaml   # pick one provider, fill in the key
make dev-backend                           # http://localhost:8000/api/docs
make dev-frontend                          # http://localhost:3000/chat
```

With no `providers.yaml`, the chat returns a clear "no chat provider
configured" error and the UI surfaces it.

## Roadmap note

This sprint delivers the chat UI on top of the Sprint-2 provider abstraction and
Sprint-4 router snapshot, superseding the original "router agent + device
control" row in `SPRINT-1.md` (device control stays deferred). RAG retrieval
remains a later sprint; the "no RAG yet" constraint keeps answers grounded
exclusively in the router JSON.
