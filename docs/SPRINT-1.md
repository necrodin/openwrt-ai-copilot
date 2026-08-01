# Sprint 1 — Project Foundation

## Scope

Sprint 1 delivers **only the project foundation**: a clean, enterprise-grade
monorepo scaffold. No router logic, no AI logic, no RAG, and no dashboard.

Everything AI-shaped exists as **interfaces, contracts, and stubs** that raise
`NotImplementedError` with a target sprint, keeping the dependency graph and
conventions in place before any real logic is written.

## Approved stack (supersedes earlier Go-based assumptions in ARCHITECTURE.md)

| Layer | Decision |
|---|---|
| Frontend | Next.js 15 (App Router), React 19, TypeScript, Tailwind CSS v4, shadcn/ui |
| Backend | FastAPI, Python 3.12 |
| Database | SQLite via SQLAlchemy 2 |
| Deployment | Docker + Docker Compose |
| AI layer | Python packages: `ai`, `providers`, `rag`, `vision` (provider-agnostic) |
| Router agent | Python package `router_agent` (scaffold only) |

Provider independence is preserved: the `ai` package defines
`Completer` / `Embedder` / `Visioner` / `Reranker` protocols and the capability
registry; the `providers` package hosts per-provider adapters (ollama, nim,
openai, openrouter, lmstudio, vllm) that will implement those protocols.

## Repository map

```
frontend/          Next.js app; landing page + backend health check (no dashboard)
backend/           FastAPI app package `app`: config, logging, exceptions, db glue,
                   v1 health/ready endpoints; SQLite init on startup
ai/                ai.core: unified data model, protocols, capability registry, errors
providers/         base.py + factory + six provider adapter placeholders
rag/               RAG pipeline stub + chunking/retrieval/reranking placeholders
vision/            Visioner protocol re-export + adapters placeholder
database/          SQLite engine/session/schema (Base + system_metadata), migrations (plan)
router-agent/      router_agent scaffold with CLI entry point (no router logic)
docker/            docker-compose.yml (backend + frontend) + .env.example
tests/             pytest suite (unit + integration)
docs/              this sprint + architecture docs
```

## Conventions

- **src layout**: each top-level directory is an independent Python distribution
  (`pyproject.toml` + `src/<package>/`). Install with `pip install -e ./<dir>`
  (one `-e` per package — a single `-e` with multiple paths only applies to the
  first). Wheel and editable installs are both verified.
- **Import rules**: `ai` depends on nothing but pydantic. `providers`, `rag`,
  `vision`, `backend` depend on `ai`. `database` depends on nothing application
  or AI related. `backend` depends on `database`. Never invert these edges.
- **No provider SDKs**: adapters will talk to standard HTTP endpoints only.
- **Python 3.12**, formatting/linting via ruff, line length 100.
- Frontend: strict TypeScript, shadcn/ui `new-york` style, Tailwind v4 CSS
  variables theme.
- SQLite is the Sprint 1 datastore; migrations are deferred until the first
  domain entities exist.

## Run it

```bash
make install         # venv + pip install -e for all packages + npm install
make dev-backend     # http://localhost:8000  (docs at /api/docs)
make dev-frontend    # http://localhost:3000
make test            # pytest
make lint            # ruff check + format check
docker compose -f docker/docker-compose.yml up --build   # full stack
```

## Roadmap

| Sprint | Deliverable |
|---|---|
| 1 (done) | Foundation: monorepo, FastAPI shell + health, Next.js shell, SQLite, Docker, provider-agnostic contracts |
| 2 (done) | Provider adapters: OpenAI-compatible core + native Ollama/NIM; model catalog; failover routing |
| 3 | RAG: ingestion, chunking, embeddings, retrieval, reranking |
| 4 (done) | Live dashboard: realtime WebSocket widgets (CPU, RAM, storage, WAN/LAN, firewall, VPN, wireless, bandwidth, devices, internet) |
| 5 | Router agent + device control: safe apply / dry-run / rollback |
| 6 | Auth, policy/guardrails, audit trail |
| 7 | Dashboard + chat UI |
