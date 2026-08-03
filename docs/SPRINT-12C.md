# Sprint 12C — Router Tool Layer in AI Chat Pipeline

Status: **complete**

## Objective

Integrate the provider-independent Router Tool layer (Sprint 12B) into the AI
chat pipeline so a router-aware request is augmented with structured router
state in the system prompt, before the user message. Read-only execution only;
no write operations and no shell commands from `ChatService`.

## Files Changed

- `backend/app/services/router_tool.py` — added `render_markdown()` producing
  structured markdown (Router, CPU, Memory, Storage, Network Interfaces) from the
  tool getters; returns `None` when no snapshot is available.
- `backend/app/api/v1/chat.py` — `_router_context_markdown()` now collects
  router state through `RouterTool`; wrapped in `try/except` so a failing tool
  never fails the chat request.
- `tests/unit/test_router_tool.py` — `render_markdown()` tests.
- `tests/unit/test_chat_api.py` — router-aware assertions updated to the
  tool-rendered markdown sections.
- `docs/SPRINT-12C.md` — this document.

## Tests Executed

- `tests/unit/test_router_tool.py` — 13 tests.
- `tests/unit/test_chat_api.py` — 14 tests.
- Result: 27 passed.

## Verification

- ruff check clean on modified files.
- ruff format --check clean on modified files.
- Frontend build not run: no frontend files changed in this sprint.
- git status clean after commit.
