# Sprint 13A — Router AI Tool Selection

Status: **complete**

## Objective

Let the AI chat pipeline automatically decide which Router Tool(s) to execute
based on the user's request, using the provider-independent Router Tool layer.
Read-only operations only; no configuration changes, no reboot, no restart, and
no write operations.

## Architecture

- `RouterToolSelector` maps a user message to the Router Tool intents it needs
  (`system`, `cpu`, `memory`, `storage`, `network`) via keyword matching. When
  no router information is required it returns an empty list and tool execution
  is skipped entirely.
- `ChatService` now owns tool selection: `router_context_markdown(message)` runs
  the selector, and only executes the selected tools through the injected
  `RouterTool`. A failing tool never fails the chat request (best-effort, returns
  `None`).
- `RouterTool.render_markdown()` gained an optional `intents` argument so only
  the selected sections are rendered into the system prompt.
- The chat API delegates to `ChatService` instead of constructing `RouterTool`
  directly. All existing Router Tool getters and rendering are reused unchanged.

## Files Changed

- `backend/app/services/router_tool_selector.py` — new selector service.
- `backend/app/services/router_tool.py` — `render_markdown(intents=None)`.
- `backend/app/services/chat_service.py` — selector-driven `router_context_markdown`.
- `backend/app/api/v1/chat.py` — delegate tool collection to `ChatService`.
- `backend/app/main.py` — inject `RouterTool` into `ChatService`.
- `tests/unit/test_router_tool_selector.py` — new selector tests.
- `tests/unit/test_router_tool.py` — selective rendering tests.
- `tests/unit/test_chat_api.py` — router-aware tests updated for selector.
- `docs/SPRINT-13A.md` — this document.

## Tests Executed

- `tests/unit/test_router_tool_selector.py` — intent resolution tests.
- `tests/unit/test_router_tool.py` — render_markdown selection tests.
- `tests/unit/test_chat_api.py` — router-aware chat integration tests.
- Result: 42 passed.

## Verification

- ruff check clean on modified files.
- ruff format --check clean on modified files.
- Frontend build not run: no frontend files changed in this sprint.
- git status clean after commit.
