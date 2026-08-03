# Changelog

All notable changes to OpenWrt AI Copilot are documented here, per sprint.

## [0.1.0] — v1.0 release audit (Sprint 25A)

- **Release audit.** Full repository audit for v1.0: removed dead code, verified
  referenced modules, and confirmed no duplicate routes or services.
- **Dead code removed**
  - Backend: `app/core/exceptions.py`, `app/core/security.py`, `app/db/session.py`,
    the empty `app/models/` package, the write-only `_manager` global in
    `provider_manager.py`, the unused `get_logger()` helper, and the dead
    `RouterTool.render_markdown()` (plus its tests) — superseded by
    `RouterSnapshotService.render_markdown()`.
  - Libraries: dead error classes (`CacheError`, `ConfigurationError`,
    `MemoryError` in `rag.errors`; `KnowledgeChunkingError`,
    `KnowledgeExtractionError` in `knowledge.errors`; `CollectorError` in
    `router_agent.errors`), the Sprint-1 stub `rag/pipeline.py` and the empty
    `rag/chunking/`, `rag/reranking/`, `rag/retrieval/` placeholder packages,
    `ProvidersConfig.from_dict()`, `create_store_factory()`, `l2_norm()`,
    `DocumentRef`, `KnowledgeMetadata.keys()/items()`, `DEFAULT_OVERLAP`,
    `SSHConfig.from_agent_config()`, `SSHCredentials.authenticate_with_key`,
    `command_tokens()`, and a pass-through `token_usage()` override.
  - Frontend: `formatTime` (duplicate of `formatClock`), `sendChatMessage` and
    `ChatCompletionResponse` (the app only uses the streaming path).
- **Bug fixes**
  - `vision` package failed to import — it referenced a non-existent `Visioner`
    protocol. Fixed to re-export `VisionProvider` from `ai.core.protocols`.
  - Unreachable `return 2` removed after `parser.error()` in the router agent CLI.
- **API completeness.** Added docstrings to all backend API handlers (`/health`,
  `/ready`, `/providers*`) and the 13 core wire models in `ai.core.models`;
  added missing type hints to `rag.ai.rerank.build_reranker()` and
  `database.config.engine_kwargs()`.
- **Release docs.** Added `README.md` (rewritten), `CHANGELOG.md`,
  `RELEASE_NOTES_v1.md`.
- Full suite: 730 passed. Ruff check + format clean. Production frontend build OK.

## [0.1.0] — unified router status contract (Sprint 24B)

- **Fixed a shadowing bug:** `/router/status` was registered twice; the legacy
  handler (`connected`, `source`, `device_id`, …) won and masked the richer
  snapshot/diagnosis/recommendations payload.
- **Merged contract:** `GET /router/status` now returns a superset —
  legacy connection-state fields plus `snapshot`, `diagnosis`,
  `recommendations`, and `server_time` — built by `router_status.py` from
  `RouterSnapshotService.latest()`.
- Removed the dead duplicate handler from `router.py`; the three legacy
  `test_router_api.py` tests now pass unmodified.
- Added regression tests (`test_router_status_api.py`): disconnected state
  (error + retained snapshot), malformed-snapshot tolerance, and coexistence of
  legacy fields with derived status.
- Full suite: 734 passed (previously 731 passed / 3 failed).

## [0.1.0] — end-to-end router pipeline tests (Sprint 24A)

- Added `tests/e2e/test_router_pipeline.py` — 16 tests covering all 12 required
  scenarios: intent detection, tool selection/execution, diagnosis,
  recommendations, RAG grounding, citations, context cache, snapshot lifecycle,
  and error paths, using the real `RouterManager` /
  `RouterSnapshotService` / diagnosis / recommendation engines with a mocked AI
  transport.
- Full router suite: 167 passed.

## [0.1.0] — router context streaming (Sprint 23B)

- Router context is now emitted once on the final `done` SSE event during
  streaming chat; the frontend attaches it to the assistant message.

## [0.1.0] — router context in final answers (Sprint 23A)

- The assistant now uses the router context when composing final answers; the
  router pipeline (generate → cache → diagnose → recommend → expose → render) is
  complete and integrated end-to-end.

## [0.1.0] — router context in chat UI (Sprint 22A)

- Displayed the Router Context used for each router-aware chat response as a
  collapsible panel below the assistant message.

## [0.1.0] — live router status panel in chat (Sprint 21A)

- Added a collapsible "Router Status" card to the Chat page, sourced from
  `GET /router/status`.

## [0.1.0] — complete router-aware chat pipeline (Sprint 20A)

- First end-to-end AI experience: router-related questions automatically trigger
  intent detection and tool execution; answers are grounded in live router data.

## [0.1.0] — live dashboard backend (Sprint 19A)

- Dashboard page connected to the live `GET /router/status` endpoint, replacing
  placeholder values.

## [0.1.0] — router status REST endpoint (Sprint 18A)

- Exposed router live state, diagnosis, and recommendations through
  `GET /router/status`.

## [0.1.0] — safe router actions (Sprint 17A)

- Added `RouterActionGuard`, which evaluates every router action and returns an
  `ActionDecision` (`allow` / `require_approval` / `deny`) before any write.

## [0.1.0] — recommendation engine (Sprint 16B)

- Deterministic recommendation engine generating prioritized, actionable
  recommendations from a `DiagnosisReport`; appended to router context.

## [0.1.0] — diagnosis engine (Sprint 16A)

- Deterministic diagnosis engine analyzing a `RouterSnapshot` and producing
  structured health findings; appended to router context automatically.

## [0.1.0] — multi-router support (Sprint 15B)

- `RouterManager` registers, lists, resolves, and defaults routers, letting
  `ChatService` work with multiple configured routers.

## [0.1.0] — router snapshot (Sprint 15A)

- Unified, immutable `RouterSnapshot` combining Router Tool results so
  `ChatService` consumes a single snapshot per request.

## [0.1.0] — router context cache (Sprint 14B)

- Cached Router Tool execution results to avoid repeated router queries during a
  conversation.

## [0.1.0] — automatic intent detection (Sprint 14A)

- Removed the manual `router_aware` flag; the pipeline now auto-detects whether
  Router Tools are needed for a request.

## [0.1.0] — tool execution engine (Sprint 13C)

- `RouterToolExecutor` runs tool requests selected by `RouterToolSelector`
  through `RouterToolRegistry`; `ChatService` executes the results.

## [0.1.0] — tool registry (Sprint 13B)

- `RouterToolRegistry` for registering and resolving Router Tools by name.

## [0.1.0] — AI tool selection (Sprint 13A)

- Automatic selection of which Router Tool(s) to execute based on the user's
  request.

## [0.1.0] — router tool layer in chat (Sprint 12C)

- Provider-independent Router Tool layer integrated into the chat pipeline.

## [0.1.0] — router tool layer (Sprint 12B)

- Provider-independent, read-only Router Tool abstraction over the Router Agent
  snapshot with structured getters.

## [0.1.0] — router context in chat (Sprint 12A)

- Router context from Sprint 11A integrated into the AI chat pipeline; a
  router-aware request is automatically grounded in live router state.

## [0.1.0] — router dashboard integration (Sprint 11A)

- First end-to-end router dashboard integration: `/router/info`,
  `/router/status`, `/router/context` endpoints.

## [0.1.0] — SSH transport layer (Sprint 10A)

- Async-native SSH transport over three interchangeable backends (asyncssh,
  paramiko, mock), with connection pooling and retries.

## [0.1.0] — retrieval → AI chat (Sprint 9B)

- RAG service (`rag.yaml`) wired into AI chat: embed → retrieve → optionally
  rerank (e.g. NVIDIA NIM) → ground → stream answers with citations, memory, and
  context expansion.

## [0.1.0] — retrieval core (Sprint 9A)

- Provider-independent retrieval core: `VectorRetriever`, `DefaultContextBuilder`,
  `DefaultPromptBuilder`, numbered citations, rolling-window memory, token
  budgeting, and caching.

## [0.1.0] — knowledge platform (Sprint 8)

- Provider-independent ingestion (`source → loader → parser → extractor →
  chunker → indexer`) for Markdown/HTML/PDF/TXT/JSON/YAML/XML, with incremental
  indexing, checksum duplicate detection, and language detection.

## [0.1.0] — vector database layer (Sprint 7)

- `VectorStore` interface with SQLite, Chroma, Qdrant, and FAISS backends behind
  a config-driven `VectorStoreFactory`.

## [0.1.0] — embedding platform (Sprint 6)

- Provider-independent `EmbeddingFactory` with batching, retries, timeouts, and
  token-usage accounting.

## [0.1.0] — AI chat (Sprint 5)

- Natural-language chat grounded in the live router snapshot, with streaming,
  chat history, and Markdown rendering.

## [0.1.0] — live dashboard (Sprint 4)

- WebSocket-driven dashboard of router state (system, CPU, memory, storage,
  network interfaces).

## [0.1.0] — provider abstraction (Sprint 2)

- Provider-agnostic AI core (`ai.core` protocols, models, registry) and adapter
  package (`providers`) for Ollama, NVIDIA NIM, OpenAI, OpenRouter, LM Studio,
  and vLLM.

## [0.1.0] — foundation (Sprint 1)

- Monorepo scaffold: FastAPI backend, Next.js frontend, packaging for all Python
  packages, Makefile, Docker compose.
