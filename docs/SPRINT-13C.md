# Sprint 13C — Router Tool Execution Engine

## Objective
Implement the Router Tool executor that runs tool requests selected by the
`RouterToolSelector` through the `RouterToolRegistry`, and wire `ChatService`
to execute those requests **only** through the executor. The executor is a
pure read-only orchestration layer: it resolves each requested tool, runs the
tools sequentially in request order, collects structured results, and keeps
going when an individual tool fails.

Scope is execution orchestration only:
- No new Router Tools.
- No Router Agent changes.
- No write operations, no shell commands.

## Architecture
```
ChatService.router_context_markdown(message)
  ├─ RouterToolSelector.select(message)      → tool requests (names)
  ├─ RouterToolExecutor.execute(requests)    → list[RouterToolResult]
  │     ├─ RouterToolRegistry.resolve(name)  → registered callable
  │     └─ run tool, capture result/failure
  └─ RouterTool.render_markdown(intents)     → markdown section
```

- `RouterToolSelector` returns tool requests only (unchanged).
- `RouterToolExecutor` accepts one or more tool requests, resolves each through
  `RouterToolRegistry`, executes sequentially, preserves order, collects
  structured `RouterToolResult` values, and never raises for an individual tool
  failure (captured in `result.ok` / `result.error`).
- `ChatService` executes requests only through `RouterToolExecutor`. When no
  requests are needed, or execution yields nothing usable, the router context
  section is skipped and the chat proceeds normally.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_tool_executor.py` | **new** — `RouterToolExecutor`, `RouterToolResult` (`name`, `ok`, `result`, `error`, `to_dict()`), `__all__`. |
| `backend/app/services/chat_service.py` | Accept optional `executor` in `__init__` (defaults from registry); `router_context_markdown` executes through the executor and renders only usable results. |
| `tests/unit/test_router_tool_executor.py` | **new** — ordering, sequential execution, failure tolerance, unknown-tool handling, structured results. |
| `tests/unit/test_chat_api.py` | Added `test_chat_router_aware_executes_through_executor` proving `ChatService` executes through the executor. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_tool_executor.py \
  tests/unit/test_router_tool_selector.py tests/unit/test_chat_api.py -o addopts="" -q
36 passed
```

## Lint
```
.venv/bin/python3 -m ruff check  backend/app/services/router_tool_executor.py \
  backend/app/services/chat_service.py tests/unit/test_router_tool_executor.py \
  tests/unit/test_chat_api.py
.venv/bin/python3 -m ruff format --check <same files>
All checks passed; 4 files already formatted
```

## Verification
- `RouterToolExecutor.execute(["system"])` returns a single ordered,
  successful `RouterToolResult`.
- Multiple requests execute sequentially and preserve request order.
- A failing tool returns `ok=False` with the error message and does not stop
  subsequent tools; unknown tools are handled without raising.
- `ChatService` runs selected requests through the executor (proven by the
  injected recording executor in `test_chat_router_aware_executes_through_executor`).
- Existing router-aware chat, streaming, and no-intent skip behaviors still pass.

## Notes / Follow-ups
- `render_markdown` re-reads the snapshot from the `RouterTool`; this keeps
  rendering logic in one place. Executor results remain the execution contract
  for future consumers.
