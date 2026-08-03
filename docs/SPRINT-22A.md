# Sprint 22A — Expose Router Context in Chat

## Objective
Display the Router Context used by the AI for each router-aware chat response as
a collapsible panel directly below the assistant message. Reuse the existing
router-aware pipeline; do not regenerate context, re-run router tools, or
duplicate markdown rendering. Normal conversations are unchanged.

## Architecture
```
POST /api/v1/chat            (non-streaming)
POST /api/v1/chat/stream     (SSE)
  ├─ router_context = _router_context_markdown(...)   (computed once)
  ├─ service.compose(router_context=router_context)
  └─ response payload  →  "router_context": router_context
        └─ non-streaming JSON body
        └─ SSE "done" event

frontend
  ├─ lib/chat.ts          ChatTurn / ChatCompletionResponse /
  │                       done-event now carry router_context?: string | null
  ├─ hooks/use-chat.ts    onDone stores event.router_context on the turn
  ├─ components/chat/message-bubble.tsx
  │     └─ RouterContextPanel (local, collapsed by default):
  │           "Router Context" chevron toggle
  │           expanded → <Markdown content={routerContext} />
  └─ app/chat/page.tsx    passes turn.router_context into <MessageBubble>
```
- The exact markdown string returned by the backend is rendered verbatim by the
  existing `Markdown` component — no re-rendering or duplication.
- The panel renders only when `router_context` is present on an assistant turn;
  absent context means no panel and no placeholder.
- Collapsed by default via local `useState`; expands to show the Snapshot,
  Diagnosis, and Recommendations sections contained in the markdown.
- Reuses existing components (`Markdown`, `Badge`, `MessageBubble`); no new
  page, no redesign.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/api/v1/chat.py` | Compute `router_context` once per request and include it in the `POST /chat` response body and the SSE `done` event of `POST /chat/stream`. |
| `frontend/lib/chat.ts` | Add optional `router_context` to `ChatTurn`, `ChatCompletionResponse`, and the streaming `done` event. |
| `frontend/hooks/use-chat.ts` | Persist `event.router_context` onto the assistant turn in `onDone`; initialize it to `null`. |
| `frontend/components/chat/message-bubble.tsx` | Add `RouterContextPanel` — collapsible (default collapsed) panel below assistant messages rendering the router context markdown when present. |
| `frontend/app/chat/page.tsx` | Pass `turn.router_context` into `MessageBubble`. |
| `tests/unit/test_chat_api.py` | Assert `router_context` present for router-aware replies (JSON + SSE) and `null` otherwise. |

## Tests Executed
- `tests/unit/test_chat_api.py` — 22 passed
- `tests/unit/test_chat_api_rag.py` — included in run, passed

## Verification
- `ruff check` passes on modified backend/test files.
- `npx eslint` passes on all modified frontend files.
- `npm run typecheck` passes.
- `npm run build` (production) succeeds; `/chat` compiles to a static route.
- Router-aware replies include `router_context` in the JSON body and the SSE
  `done` event; non-router and unavailable-router replies return `null`.
