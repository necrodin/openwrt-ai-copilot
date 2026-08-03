# Sprint 12A — Router Context in AI Chat Pipeline

Status: **complete**

## Objective

Integrate the router context generated in Sprint 11A into the AI chat pipeline so
a chat request marked as router-aware automatically receives the current router
context in its system prompt — without changing behavior for ordinary
conversations or failing when the router is unavailable.

## Implementation

### Router-aware flag (`backend/app/schemas/chat.py`)

- `ChatRequestBody.router_aware: bool = False` — when `True` the request opts in
  to router-context injection. Default keeps every existing conversation
  byte-for-byte unchanged.

### Context collection (`backend/app/api/v1/chat.py`)

- New helper `_router_context_markdown(request)`: reads the snapshot service from
  app state, calls the existing `build_context()` from `router_context.py`, and
  returns its `markdown` when a snapshot is available.
- Best-effort by design: missing service or no snapshot returns `None`, so a
  router-aware request proceeds exactly like a normal one.
- Injected only on the non-RAG chat path (`/chat` and `/chat/stream`) via the
  `router_context` argument to `ChatService.compose()`. The opt-in RAG path is
  untouched.

### System prompt injection (`backend/app/services/chat_service.py`)

- `ChatService.compose()` gained an optional `router_context` keyword: when
  provided the markdown is appended to the system prompt under a
  `ROUTER CONTEXT:` heading; when omitted the system prompt is unchanged.

## Files Changed

- `backend/app/schemas/chat.py` — `router_aware` field.
- `backend/app/api/v1/chat.py` — context collection helper + wiring.
- `backend/app/services/chat_service.py` — `compose(..., router_context=None)`.
- `tests/unit/test_chat_api.py` — router-aware chat tests.
- `docs/SPRINT-12A.md` — this document.

## Tests

- `test_chat_router_aware_injects_router_context` — populated snapshot -> context
  markdown in system prompt, user message last.
- `test_chat_not_router_aware_no_router_context` — default request unchanged.
- `test_chat_router_aware_unavailable_router_continues` — no snapshot -> normal
  reply, no injection, no failure.
- `test_chat_stream_router_aware_injects_router_context` — streaming variant.
- `test_compose_accepts_router_context` — service-level unit test.

## Verification

- 601 pytest tests pass (all)
- ruff check clean
- ruff format --check clean
- Next.js production build passes
- git status clean after commit
