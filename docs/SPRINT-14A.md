# Sprint 14A — Automatic Router Intent Detection

## Objective
Remove the need to manually specify `router_aware`. The chat pipeline now
automatically determines whether Router Tools are required for a user request,
skipping Router Tool execution entirely when the request is unrelated to the
router.

## Architecture
```
ChatService.router_context_markdown(message, router_aware=None)
  ├─ RouterIntentDetector.classify(message)   → "router" | "non-router"
  │     └─ RouterToolSelector.select(message) (reused, no duplicated logic)
  ├─ RouterToolSelector.select(message)        → tool requests
  ├─ RouterToolExecutor.execute(requests)      → list[RouterToolResult]
  └─ RouterTool.render_markdown(intents)       → markdown section
```

- `RouterIntentDetector` is a lightweight, deterministic classifier: a request
  is `router` when the existing `RouterToolSelector` finds at least one Router
  Tool intent, otherwise `non-router`. No LLM involved.
- For `router` requests, the existing `RouterToolSelector` is reused as-is;
  selection logic is not duplicated.
- For `non-router` requests, Router Tool execution is skipped entirely.
- `router_aware` in the chat body remains only as an optional override:
  `None` (default) auto-detects, `true` forces the router layer, `false` skips it.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_intent_detector.py` | **new** — `RouterIntentDetector` with `classify(message)` returning `"router"`/`"non-router"`, reusing `RouterToolSelector`. |
| `backend/app/services/chat_service.py` | Accept optional `detector` (defaults from the selector); `router_context_markdown` auto-detects intent and honors the `router_aware` override. |
| `backend/app/schemas/chat.py` | `router_aware` is now `bool | None = None` (auto-detect by default) with a docstring. |
| `backend/app/api/v1/chat.py` | Both `/chat` and `/chat/stream` call `_router_context_markdown` unconditionally, passing the override. |
| `tests/unit/test_router_intent_detector.py` | **new** — router vs non-router classification, registry reuse, default detector behavior. |
| `tests/unit/test_chat_api.py` | Reworked router-aware tests to exercise auto-detection (inject and skip without `router_aware`). |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_intent_detector.py \
  tests/unit/test_chat_api.py -o addopts="" -q
20 passed
```

## Lint
```
.venv/bin/python3 -m ruff check  backend/app/services/router_intent_detector.py \
  backend/app/services/chat_service.py backend/app/api/v1/chat.py \
  backend/app/schemas/chat.py tests/unit/test_router_intent_detector.py \
  tests/unit/test_chat_api.py
.venv/bin/python3 -m ruff format --check <same files>
All checks passed; 6 files already formatted
```

## Verification
- Router requests (e.g. "show router system info", "what is the cpu usage?",
  "how much memory is free") classify as `router` and inject ROUTER CONTEXT.
- Non-router requests ("hello there", "what is 2 + 2?") classify as
  `non-router` and skip Router Tool execution — no ROUTER CONTEXT, and no tool
  execution happens.
- `/chat` and `/chat/stream` auto-detect intent without any `router_aware` flag.
- The `router_aware` override still works for callers that need forced behavior.
- Frontend build not run: no frontend files changed.
