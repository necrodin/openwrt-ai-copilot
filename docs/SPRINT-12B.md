# Sprint 12B — Provider-Independent Router Tool Layer

Status: **complete**

## Objective

Implement a provider-independent, read-only Router Tool abstraction over the
existing Router Agent snapshot, exposing structured getters for system, CPU,
memory, storage, and network information. No write operations, no reboot, no
restart, no configuration changes, and no new frontend features.

## Architecture

- `RouterTool` (backend service) is a thin read-only facade. It is constructed
  with a `latest()` callable returning the newest `DashboardUpdate` (or `None`
  when nothing has been collected yet) and rebuilds its view on every getter.
- All OpenWrt-specific collection stays inside `router-agent`; the tool never
  runs or exposes shell commands to `ChatService`.
- Structured extraction is reused from `router_context.build_context()`, so the
  tool and the AI chat context share one source of truth and cannot drift.
- Exposes: `available`, `get_system_info()`, `get_cpu_info()`,
  `get_memory_info()`, `get_storage_info()`, `get_network_info()`.

## Files Changed

- `backend/app/services/router_tool.py` — new `RouterTool` abstraction.
- `tests/unit/test_router_tool.py` — unit tests for the tool layer.

## Tests Executed

- `tests/unit/test_router_tool.py` — 11 tests (available/unavailable states, all
  five getters, empty-snapshot behavior, no shared-mutation, read-only surface).
- Result: 11 passed.

## Verification

- ruff check clean on modified files.
- ruff format --check clean on modified files.
- Frontend build not run: no frontend files changed in this sprint.
- git status clean after commit.
