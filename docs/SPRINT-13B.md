# Sprint 13B — Router Tool Registry

Status: **complete**

## Objective

Implement a Router Tool Registry responsible for registering and resolving Router
Tools by name. No new Router Tools, no Router Agent behavior changes, and no write
operations.

## Architecture

- `RouterToolRegistry` is the single source of truth for available Router Tools:
  - `register(name, tool)` — registers a tool, rejecting duplicates with
    `DuplicateRouterToolError`.
  - `resolve(name)` — returns the registered tool or raises `UnknownRouterToolError`
    for unknown names.
  - `available` — lists all registered tool names.
- `RouterToolSelector` now resolves intents against a registry: only intents
  registered in the underlying registry are considered, so selection follows the
  registry's available tools instead of referencing Router Tool implementations
  directly.
- `ChatService` builds the registry from its `RouterTool` getters (system, cpu,
  memory, storage, network) and wires it into the selector. All existing Router
  Tool getters and rendering are reused unchanged.

## Files Changed

- `backend/app/services/router_tool_registry.py` — new registry service.
- `backend/app/services/router_tool_selector.py` — registry-backed selection.
- `backend/app/services/chat_service.py` — builds and wires the registry.
- `tests/unit/test_router_tool_registry.py` — new registry tests.
- `tests/unit/test_router_tool_selector.py` — registry-aware selector tests.
- `docs/SPRINT-13B.md` — this document.

## Tests Executed

- `tests/unit/test_router_tool_registry.py` — registration, resolution,
  duplicates, unknown-tool error, available tools.
- `tests/unit/test_router_tool_selector.py` — registry-backed intent resolution.
- `tests/unit/test_router_tool.py` and `tests/unit/test_chat_api.py` — unaffected
  suites re-run to confirm no regressions.
- Result: 49 passed.

## Verification

- ruff check clean on modified files.
- ruff format --check clean on modified files.
- Frontend build not run: no frontend files changed in this sprint.
- git status clean after commit.
