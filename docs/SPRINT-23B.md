# Sprint 23B — Stream Router Context Updates

## Objective
Support Router Context during streaming responses. Router context is emitted
exactly once, attached to the final `done` event of the SSE stream, and the
frontend streaming hook captures it to update the current assistant message.
The streaming contract stays backward compatible.

## Architecture
```
POST /api/v1/chat/stream  (SSE generator)
  ├─ router_context = _router_context_markdown(...)      (computed once)
  ├─ service.compose(router_context=router_context)
  ├─ delta events → {"type": "delta", "content": ...}    (no router_context)
  └─ done event   → {"type": "done", "reply", "provider",
                     "model", "usage", "router_context"}  (exactly once)

frontend
  ├─ lib/chat.ts      done-event type carries optional router_context?: string | null
  └─ hooks/use-chat.ts onDone → router_context: event.router_context ?? null
```
- Router context is never duplicated on individual streamed tokens; only the
  final `done` event carries it.
- `router_context` is optional in the event type, so the SSE protocol is
  backward compatible: clients that do not read the field continue to work
  unchanged, and the `?? null` fallback keeps existing messages intact.
- No changes to RouterManager, RouterExecutor, RouterTools, Diagnosis,
  Recommendation, Snapshot, or Intent Detection. No new endpoints.

## Files Changed
| File | Change |
| --- | --- |
| `tests/unit/test_chat_api.py` | Add `_sse_events` helper plus `test_chat_stream_router_context_emitted_once_on_done`, `test_chat_stream_tokens_remain_unchanged`, and `test_chat_stream_without_router_context_stays_null`. |

The backend streaming endpoint (`backend/app/api/v1/chat.py`) and frontend
plumbing (`frontend/lib/chat.ts`, `frontend/hooks/use-chat.ts`) already carry
the exact-once `router_context` in the `done` event from Sprint 22A; this
sprint locks that contract down with tests.

## Tests Executed
- `tests/unit/test_chat_api.py` + `tests/unit/test_chat_api_rag.py` — 27 passed.
- New tests prove: `router_context` appears exactly once in the stream (only on
  `done`, never on `delta`); streamed tokens and the final reply are unchanged;
  a non-router stream still emits a valid `done` event with `router_context:
  null` (clients without router-context support keep working).

## Verification
- `ruff check` passes on the modified test file and `chat.py`.
- `ruff format --check` passes (both files already formatted).
