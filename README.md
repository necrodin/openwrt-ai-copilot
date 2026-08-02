# OpenWrt AI Copilot

A production-grade, provider-independent AI copilot for managing OpenWrt router
fleets. Ask questions about your network in natural language, diagnose
connectivity issues, and — under strict human approval — propose and apply
validated configuration changes.

**The AI layer is fully provider-independent.** Supported providers (Ollama,
NVIDIA NIM, OpenAI, OpenRouter, LM Studio, vLLM) are interchangeable adapters,
never hard dependencies.

> **Sprint 5 delivered: AI Chat.** Ask questions about your router in natural
> language; answers are grounded in the live router snapshot, never invented.
> Streaming, chat history, and Markdown rendering are included. No RAG yet.
> See [docs/SPRINT-5.md](docs/SPRINT-5.md).
>
> **Sprint 6 delivered: Embedding Platform.** A provider-independent
> `EmbeddingFactory` embeds text through any configured provider (NV-Embed,
> OpenAI, Ollama, OpenRouter, LM Studio, vLLM) with batching, retries,
> timeouts, and token-usage accounting. No vector DB / RAG yet.
> See [docs/SPRINT-6.md](docs/SPRINT-6.md).
>
> **Sprint 7 delivered: Vector Database Layer.** A provider-independent
> `VectorStore` interface with four interchangeable backends — SQLite (offline
> reference), Chroma, Qdrant, FAISS — covering collection/document CRUD, batch
> insert, cosine similarity search, metadata filters, namespaces, pagination,
> and versioning, all behind a config-driven `VectorStoreFactory`. No RAG yet.
> See [docs/SPRINT-7.md](docs/SPRINT-7.md).
>
> **Sprint 8 delivered: Knowledge Platform.** A provider-independent knowledge
> ingestion pipeline (`source → loader → parser → extractor → chunker →
> indexer`) that turns Markdown, HTML, PDF, TXT, JSON, YAML, and XML documents
> into chunked, versioned, metadata-rich `KnowledgeDocument`s — from the OpenWrt
> catalog, local files, or in-memory sources. Incremental indexing, checksum
> duplicate detection, pure-Python language detection, and an optional
> filesystem-persisted indexer. No Retrieval / RAG yet.
> See [docs/SPRINT-8.md](docs/SPRINT-8.md).
>
> **Sprint 9A delivered: Retrieval Core.** The provider-independent retrieval
> side of RAG: `VectorRetriever` (embed → search → merge → dedupe → rank),
> `DefaultContextBuilder`, `DefaultPromptBuilder`, numbered citations,
> rolling-window conversation memory with compression and snapshots, token
> budgeting with automatic context reduction, and TTL/checksum-keyed caching.
> The pipeline ends at a ready-for-LLM `PromptRequest`/`PromptResponse` — no LLM
> connection, no streaming. See [docs/SPRINT-9A.md](docs/SPRINT-9A.md).
>
> **Sprint 9B delivered: Retrieval → AI Chat integration.** The retrieval engine
> is wired into AI Chat as an opt-in RAG service (`rag.yaml`): queries are
> embedded, retrieved, optionally reranked (e.g. NVIDIA NIM), grounded into the
> prompt, and answered with streaming — every reply carrying citations with
> similarity/rerank scores, per-conversation memory, and context expansion. The
> existing router-state chat remains the default. See
> [docs/SPRINT-9B.md](docs/SPRINT-9B.md).

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS v4, shadcn/ui |
| Backend | FastAPI, Python 3.12 |
| Database | SQLite (via SQLAlchemy 2) |
| AI layer | Provider-agnostic Python packages (`ai`, `providers`, `rag`, `vision`, `vectorstore`, `knowledge`) |
| Deployment | Docker, Docker Compose |

## Repository layout

```
openwrt-ai/
├── frontend/          Next.js web UI (home, live dashboard, AI chat)
├── backend/           FastAPI control plane (app package)
├── ai/                Provider-agnostic AI core: protocols, models, registry
├── providers/         Provider adapters (ollama, nim, openai, openrouter, lmstudio, vllm, nvembed)
├── rag/               Retrieval core (retriever, context, prompt, memory, tokens, cache, rerank, rag.ai integration)
├── vision/            Vision abstraction + adapters
├── vectorstore/       Provider-independent vector DB layer (sqlite, qdrant, chroma, faiss)
├── knowledge/         Provider-independent knowledge platform (sources, parsers, chunkers, indexers)
├── database/          SQLite schema, engine, session, migrations (future)
├── router-agent/      On-device agent (data collection)
├── docker/            Docker Compose topologies
├── tests/             Integration/unit tests (pytest)
└── docs/              Architecture + sprint documentation
```

## Quickstart

### 1. Backend (Python 3.12+)

```bash
make install          # create .venv, install all python packages, npm install
make dev-backend      # uvicorn on http://localhost:8000
```

Verify: `curl http://localhost:8000/api/v1/health`

### 2. Frontend

```bash
make dev-frontend     # Next.js dev server on http://localhost:3000
```

The frontend proxies `/api/*` to the backend (default `http://localhost:8000`).
The live dashboard is at `/dashboard`; the AI chat is at `/chat`.

### 3. Tests & linting

```bash
make test             # pytest (tests/)
make lint             # ruff check + format
make format           # ruff format
```

### 4. Docker (full stack)

```bash
docker compose -f docker/docker-compose.yml up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/api/docs

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture
- [docs/SPRINT-1.md](docs/SPRINT-1.md) — Sprint 1 scope and roadmap
- [docs/SPRINT-2.md](docs/SPRINT-2.md) — provider abstraction layer
- [docs/SPRINT-4.md](docs/SPRINT-4.md) — live dashboard
- [docs/SPRINT-5.md](docs/SPRINT-5.md) — AI chat
- [docs/SPRINT-6.md](docs/SPRINT-6.md) — embedding platform
- [docs/SPRINT-7.md](docs/SPRINT-7.md) — vector database layer
- [docs/SPRINT-8.md](docs/SPRINT-8.md) — knowledge platform
- [docs/SPRINT-9A.md](docs/SPRINT-9A.md) — retrieval core
- [docs/SPRINT-9B.md](docs/SPRINT-9B.md) — retrieval → AI chat integration
- [docs/README.md](docs/README.md) — documentation index

## License

Open-source. TBD.
