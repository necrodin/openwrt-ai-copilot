# Sprint 14B — Router Context Cache

## Objective
Cache Router Tool execution results to avoid unnecessary repeated router queries
during a conversation. `ChatService` consults the cache before invoking
`RouterToolExecutor` and reuses valid cached results whenever possible.

## Architecture
```
ChatService.router_context_markdown(message, router_aware=None, session_id=None)
  ├─ RouterIntentDetector.classify(message)   → "router" | "non-router"
  ├─ RouterToolSelector.select(message)        → tool requests
  ├─ ChatService._collect_results(session_id, requests)
  │     ├─ RouterContextCache.get(session_id, name)   → valid cached result or miss
  │     ├─ RouterToolExecutor.execute(pending)        → only uncached/expired tools
  │     └─ RouterContextCache.set(session_id, name, result)  → successful only
  └─ RouterTool.render_markdown(intents)       → markdown section
```

- `RouterContextCache` is an in-memory, dependency-free TTL cache keyed by
  (session_id, tool name), default TTL 30 seconds.
- Successful results are cached; failed executions are never cached.
- Expired entries are automatically ignored (treated as misses) and pruned.
- The cache preserves the existing `RouterToolResult` format.
- Hit/miss statistics are exposed via `stats()`.
- `ChatService._collect_results` reuses valid cached entries in place and only
  executes tools that are uncached or expired; result order matches the request
  order.
- `RouterToolExecutor`, Router Tools, and the Router Agent are unchanged.

## Files Changed
| File | Change |
| --- | --- |
| `backend/app/services/router_context_cache.py` | **new** — `RouterContextCache` with `get`/`set`/`stats`/`clear`, per-session keys, TTL expiry, success-only caching. |
| `backend/app/services/chat_service.py` | Accept optional `cache` (defaults to `RouterContextCache()`); `router_context_markdown` takes `session_id` and consults the cache via `_collect_results` before executing. |
| `backend/app/api/v1/chat.py` | `_router_context_markdown` passes `session_id` through for both `/chat` and `/chat/stream`. |
| `tests/unit/test_router_context_cache.py` | **new** — TTL, per-session scoping, failure exclusion, hit/miss stats, clear semantics. |
| `tests/unit/test_chat_api.py` | Added `test_chat_router_aware_reuses_cached_results` proving the executor is not re-invoked when cached results are valid. |

## Tests Executed
```
.venv/bin/python3 -m pytest tests/unit/test_router_context_cache.py \
  tests/unit/test_chat_api.py -o addopts="" -q
25 passed
```

## Lint
```
.venv/bin/python3 -m ruff check  backend/app/services/router_context_cache.py \
  backend/app/services/chat_service.py backend/app/api/v1/chat.py \
  tests/unit/test_router_context_cache.py tests/unit/test_chat_api.py
.venv/bin/python3 -m ruff format --check <same files>
All checks passed; 5 files already formatted
```

## Verification
- First request in a session executes the tool through the executor and caches
  the successful result; a second request asking about the same tool reuses the
  cache without re-invoking the executor.
- Failed tool executions are never cached, so they are re-executed on the next
  request.
- Expired entries (TTL elapsed) are ignored and trigger a fresh execution.
- Cache entries are scoped per session: different sessions do not share results.
- Hit/miss statistics are available and accurate.
- No external dependencies introduced; `RouterToolExecutor`, Router Tools, and
  Router Agent are unchanged.
- Frontend build not run: no frontend files changed.
