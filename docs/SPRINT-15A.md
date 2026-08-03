# Sprint 15A — Router Snapshot

## Objective
Implement a unified, immutable snapshot object representing the current router
state, combining existing Router Tool results so `ChatService` consumes a single
`RouterSnapshot` instead of individual tool outputs.

## Architecture
```
ChatService.router_context_markdown(message, router_aware=None, session_id=None)
  ├─ RouterIntentDetector.classify(message)    → "router" | "non-router"
  ├─ RouterToolSelector.select(message)         → tool requests
  ├─ RouterSnapshotService.build(executor, session_id, requests) → RouterSnapshot
  │     ├─ RouterContextCache.get(session_id, name)   → valid cached result or miss
  │     ├─ RouterToolExecutor.execute(pending)        → only uncached/expired tools
  │     └─ RouterContextCache.set(session_id, name, result)  → successful only
  └─ RouterSnapshotService.render_markdown(snapshot, intents) → markdown section
```

- `RouterSnapshot` is a frozen dataclass exposing structured sections:
  `system`, `cpu`, `memory`, `storage`, `network`, `wifi`. Sections that are
  unavailable (not requested, missing, or failed) are `None`. `to_dict()`
  serializes it with nulls for missing sections.
- `RouterSnapshotService.build` combines Router Tool results into one snapshot,
  consulting `RouterContextCache` first so no tool is executed twice and
  successful results are reused; it shares the cache instance used by
  `ChatService`.
- `ChatService` builds the snapshot and renders it directly; the duplicated
  `_collect_results` helper was removed. `RouterToolExecutor`, Router Tools, and
  the Router Agent are unchanged.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_snapshot.py` | **new** — `RouterSnapshot` (frozen, nullable sections, `to_dict()`) and `RouterSnapshotService` (`build`/`render_markdown`). |
| `backend/app/services/chat_service.py` | Consumes `RouterSnapshot` via `RouterSnapshotService`; removed `_collect_results`. |
| `tests/unit/test_router_snapshot.py` | **new** — combining results, null sections, failed sections, no double execution, per-session cache reuse, immutability, rendering. |
| `tests/unit/test_chat_api.py` | Router-aware chat tests unchanged and still green against the snapshot path. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_snapshot.py \
  tests/unit/test_chat_api.py -o addopts="" -q
26 passed
```

## Lint
```
.venv/bin/python3 -m ruff check  backend/app/services/router_snapshot.py \
  backend/app/services/chat_service.py tests/unit/test_router_snapshot.py \
  tests/unit/test_chat_api.py
.venv/bin/python3 -m ruff format --check <same files>
All checks passed; 4 files already formatted
```

## Verification
- A snapshot combining all five tools exposes `system`, `cpu`, `memory`,
  `storage`, and `network` data; `wifi` is `None` (no wifi tool).
- Unrequested or failed sections are `None` (represented as null).
- Cached tools are not executed again on a second `build` within the same
  session; results are reused via `RouterContextCache`.
- `RouterSnapshot` is immutable (attribute assignment raises).
- `render_markdown` renders only the selected intents and returns `None` for an
  empty snapshot.
- `ChatService` renders router context from the snapshot; existing
  router-aware chat behavior is unchanged.
- Frontend build not run: no frontend files changed.
