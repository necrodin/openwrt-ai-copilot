# Sprint 15B — Multi-Router Support

## Objective
Allow `ChatService` to work with multiple configured routers by introducing a
`RouterManager` that registers, lists, resolves, and defaults routers — while
leaving existing single-router behaviour unchanged.

## Architecture
```
main.py
  └─ RouterManager
       ├─ register("default", RouterTool(snapshot_service.latest), default=True)
       └─ application.state.router_manager / ChatService(router_manager=...)

ChatService.router_context_markdown(message, router_aware, session_id, router_id)
  ├─ _resolve_router(router_id)  → RegisteredRouter (or None for unknown ids)
  │     ├─ RouterManager.resolve(router_id)      (UnknownRouterError → None)
  │     └─ RouterManager.default                 (router_id omitted)
  ├─ RegisteredRouter.selector.select(message)   → tool requests
  ├─ RegisteredRouter.snapshot_service.build(router.executor, session_id, requests)
  │     ├─ RegisteredRouter.cache  (RouterContextCache, per-router)
  │     └─ RouterToolExecutor (per-router)
  └─ RegisteredRouter.snapshot_service.render_markdown(snapshot, intents) → markdown
```

- `RouterManager` is a lightweight, in-memory registry of routers. Each router
  is registered with an id and a `RouterTool`, and gets its own dedicated
  `RouterToolRegistry`, `RouterToolSelector`, `RouterIntentDetector`,
  `RouterToolExecutor`, `RouterContextCache`, and `RouterSnapshotService`, so
  snapshot/cache/executor always operate against the selected router instance.
- `RouterManager.register` marks the first router (or an explicit `default=True`)
  as the default; `list()` lists ids; `resolve(router_id)` raises
  `UnknownRouterError` for unknown ids; `default` exposes the default router.
- `ChatService` accepts an optional `router_manager`. When one is configured,
  router context operates against the resolved router. Without one, the
  existing single-router path is preserved exactly (built-in registered router).
- No persistence introduced; everything stays in-memory.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_manager.py` | **new** — `RouterManager`, `RegisteredRouter`, `UnknownRouterError`, `DuplicateRouterError`. |
| `backend/app/services/chat_service.py` | Accept `router_manager`; resolve the selected router per request; reuse `RouterManager.build_registry`; preserve single-router path. |
| `backend/app/main.py` | Build a `RouterManager`, register the default router, expose it on app state. |
| `backend/app/schemas/chat.py` | Added optional `router_id` field. |
| `backend/app/api/v1/chat.py` | `_router_context_markdown` passes `router_id` for both `/chat` and `/chat/stream`. |
| `tests/unit/test_router_manager.py` | **new** — register/list/resolve/default/validation, per-router isolation. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_manager.py \
  tests/unit/test_chat_api.py -o addopts="" -q
26 passed
```

## Lint
```
.venv/bin/python3 -m ruff check  backend/app/services/router_manager.py \
  backend/app/services/chat_service.py backend/app/main.py \
  backend/app/api/v1/chat.py backend/app/schemas/chat.py \
  tests/unit/test_router_manager.py tests/unit/test_chat_api.py
.venv/bin/python3 -m ruff format --check <same files>
All checks passed; 7 files already formatted
```

## Verification
- `RouterManager` registers routers, lists their ids, resolves by identifier,
  exposes a default (first registered or explicitly marked), and raises
  `UnknownRouterError` for unknown ids / empty registries.
- Duplicate registration is rejected; each router gets an isolated
  `RouterContextCache`, `RouterToolExecutor`, and `RouterSnapshotService`.
- `ChatService` resolves the selected router per request (`router_id` or the
  default) and renders router context against that router's instances; unknown
  ids yield no router context instead of failing.
- With a single configured router, behaviour is unchanged: existing
  router-aware chat tests still pass through the built-in registered router.
- No Router Agent protocol changes, no duplicated Router Tool implementations,
  no persistence.
- Frontend build not run: no frontend files changed.
