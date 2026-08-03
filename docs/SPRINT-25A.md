# Sprint 25A — Final Release Audit

## Objective
Finalize the repository for the v1.0 release: detect and remove dead,
unreachable, duplicated, or obsolete code and TODO/FIXME markers; verify that
every referenced module, type hint, docstring, and exported model is real;
confirm there are no duplicate routes or services; generate the release
documentation (`README.md`, `CHANGELOG.md`, `RELEASE_NOTES_v1.md`); and ship a
clean tree — full tests, lint, format, and production frontend build all green.

## Scope
- Remove dead code only. **No feature additions. No architectural changes. No
  refactoring unless required to remove dead code.**
- Fix only issues discovered during the audit.

## Audit
A sweep of the entire repository (backend, all library packages, router-agent,
frontend) was run across five parallel audit passes:

1. Backend (`backend/app`)
2. `ai` + `providers`
3. `knowledge` + `router-agent`
4. `rag` + `vision` + `database` + `vectorstore`
5. Frontend (`frontend/`)

Findings were triaged into **removed**, **fixed**, and **intentionally kept**
(reported here for the record).

### TODO/FIXME sweep
Exactly **one** marker exists in the entire repo:
`backend/app/core/config.py:47` — `TODO(Sprint 2+): move to a proper secrets
manager; never log this value.` This is a genuine future-hardening note, not a
stale marker. **Kept.**

## Removed (dead code)

| Location | What | Why dead |
| --- | --- | --- |
| `backend/app/core/exceptions.py` | whole module | Never imported; exception handlers never wired in |
| `backend/app/core/security.py` | whole module (`derive_secret_key`) | Never imported |
| `backend/app/db/session.py` | `get_db()` / `DbSession` | Never imported; shadows the real `database.session` |
| `backend/app/models/` | empty placeholder package | Never imported |
| `backend/app/core/logging.py` | `get_logger()` | No callers (kept `configure_logging`, which is used) |
| `backend/app/services/provider_manager.py` | write-only `_manager` global | Assigned, never read |
| `backend/app/services/router_tool.py` | `render_markdown()` + `_format_kb()` | Dead in production; superseded by `RouterSnapshotService.render_markdown()`. 4 covering tests removed. |
| `rag/src/rag/pipeline.py` | whole module (`RAGPipeline`, `RetrievedChunk`) | Sprint-1 stub, never imported |
| `rag/src/rag/chunking/`, `rag/reranking/`, `rag/retrieval/` | empty placeholder packages | Never referenced |
| `rag/src/rag/errors.py` | `CacheError`, `MemoryError`, `ConfigurationError` | Defined + re-exported only, never raised/caught |
| `rag/src/rag/prompt.py` | `DocumentRef` | Dead, not exported |
| `knowledge/src/knowledge/errors.py` | `KnowledgeChunkingError`, `KnowledgeExtractionError` | Defined + re-exported only |
| `knowledge/src/knowledge/models.py` | `KnowledgeMetadata.keys()/items()` | No callers |
| `knowledge/src/knowledge/config.py` | `DEFAULT_OVERLAP` | Never read |
| `router-agent/.../transport/base.py` | `command_tokens()` (+ `shlex` import) | Zero callers |
| `router-agent/.../errors.py` | `CollectorError` | Zero references |
| `router-agent/.../transport/ssh/config.py` | `SSHConfig.from_agent_config()`, `SSHCredentials.authenticate_with_key` | Zero callers (removed the sole `AgentConfig` import) |
| `providers/.../config.py` | `ProvidersConfig.from_dict()` | Never called (kept `from_file`) |
| `providers/.../compat_provider.py` | pass-through `token_usage()` override | Pure `super()` delegation, adds nothing |
| `vectorstore/.../factory.py` | `create_store_factory()` | Only in `__all__`, never imported |
| `vectorstore/.../backends/_math.py` | `l2_norm()` | Only in `__all__` |
| `frontend/lib/dashboard-utils.ts` | `formatTime()` | Duplicate of `formatClock` |
| `frontend/lib/chat.ts` | `sendChatMessage()`, `ChatCompletionResponse` | Dead; frontend only uses the streaming path |

## Fixed (issues discovered during the audit)

- **Broken `vision` import (critical).** `vision/src/vision/__init__.py` and
  `vision/protocols.py` imported a non-existent `Visioner` protocol from
  `ai.core.protocols`, so any `import vision` raised `ImportError`. Nothing
  imports `vision` in production (latent), but the package must at least be
  importable. Fixed both files to re-export `VisionProvider` (the real
  protocol, `ai/core/protocols.py:114`). `vision` now imports cleanly.
- **Unreachable code.** `router_agent/main.py` had `return 2` after
  `parser.error(...)` (which always raises `SystemExit`). Removed.
- **Missing docstrings on public API.** Added to all backend HTTP handlers
  (`/health`, `/ready`, and the six `/providers*` handlers) and to the 13 core
  wire models in `ai/core/models.py` (`ChatMessage`, `ChatRequest`,
  `ChatResponse`, `ChatChunk`, `ModelInfo`, `EmbeddingRequest`,
  `EmbeddingVector`, `EmbeddingResponse`, `VisionRequest`, `VisionResponse`,
  `RerankRequest`, `RerankResult`, `RerankResponse`).
- **Missing type hints.** `rag/ai/rerank.py::build_reranker()` now annotates
  `manager: ProviderManager` and `configuration: RetrievalConfig` (via
  `TYPE_CHECKING`); `database/config.py::engine_kwargs()` returns
  `dict[str, Any]`.

## Verified clean (no action needed)

- **No duplicate routes.** The 24B `/router/status` shadowing was already
  resolved; every other path is registered exactly once.
- **No duplicate services.** The `rag` + `rag.ai` pairs (`engine`, `cache`,
  `config`, `models`, `errors`, `session`, `memory`, `reranker` vs `rerank`)
  are distinct layers — both sides are consumed by
  `backend/app/services/rag_service.py`, not duplicates.
- **RAG over full suite:** `rag.errors` exceptions referenced by tests
  (`ContextLimitError`, `EmbeddingError`, `RetrieverError`, `CollectionError`)
  were retained; only the unreferenced ones were removed.
- **`banner_timeout`** in `router-agent` is live — `backends.py` passes it to
  the asyncssh backend. Not removed.

## Intentionally kept (documented)

- **Capability registry** (`ai/core/registry.py`). Only `register()` is called
  (by `ProviderManager._register_capabilities`); the registry is currently
  write-only. Its docstring declares it planned infrastructure ("providers
  register themselves in later sprints"), so removal would be an architectural
  change — out of scope. Kept.
- **Test-only APIs** — small public helpers exercised only by tests but part of
  their model's natural API: `TokenUsage.total_tokens`,
  `KnowledgeCollectionConfig.effective_chunking()`, `IndexResult.changed`,
  `RouterContextCache.stats()` / `clear()`. Kept.
- **shadcn/ui-style exports** (`badgeVariants`, `buttonVariants`,
  `skeletonVariants`) and exported types that are only used internally — the
  shadcn convention; removal is churn without value. Kept.
- **TODO at `config.py:47`** — genuine future hardening, kept.
- **Duplicated format helpers** (`_format_kb` / `_format_bytes` appearing in
  several services) and duplicated frontend page helpers — consolidation is
  refactoring, not dead-code removal. Left in place.
- **`RouterSnapshot.wifi` always `None`** → diagnosis always emits a "Missing
  WiFi" finding when a network is present. Wiring a real WiFi collector is
  future work, not a dead-code fix. Documented in RELEASE_NOTES_v1.md.

## Release Documentation
- `README.md` — rewritten for the v1.0 feature set (router agent, router-aware
  chat, diagnosis/recommendations, full public API table, quickstart).
- `CHANGELOG.md` — created; full sprint history (Sprint 1 → 25A).
- `RELEASE_NOTES_v1.md` — created; highlights, included components, known
  limitations, migration notes.

## Tests Executed
- Full project suite: **730 passed** (734 − 4 removed `render_markdown` tests).
- Command: `.venv/bin/python3 -m pytest -o addopts="" -q`.
- `ruff check .` — clean.
- `ruff format --check .` — clean (292 files).
- Frontend production build: `npm run build` — compiled successfully, all 6
  static pages generated, type-check passed.
- `import vision` — verified importable after the `VisionProvider` fix.

## Files Changed (summary)
- Removed: 4 backend modules, `rag/pipeline.py` + 3 placeholder packages, and
  3 frontend exports (in 2 files).
- Edited: ~20 source files across backend, libraries, router-agent, and
  frontend; `tests/unit/test_router_tool.py` (4 removed tests).
- Docs: `README.md`, `CHANGELOG.md`, `RELEASE_NOTES_v1.md`, `docs/SPRINT-25A.md`.
