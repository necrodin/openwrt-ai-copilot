# OpenWrt AI Copilot

A production-grade, provider-independent AI copilot for managing OpenWrt router
fleets. Ask questions about your network in natural language, diagnose
connectivity issues, and — under strict human approval — propose and apply
validated configuration changes.

**The AI layer is fully provider-independent.** Supported providers (Ollama,
NVIDIA NIM, OpenAI, OpenRouter, LM Studio, vLLM) are interchangeable adapters,
never hard dependencies.

> This repository is in **Sprint 1: project foundation**. No router logic, AI
> logic, RAG, or dashboard is implemented yet. See
> [docs/SPRINT-1.md](docs/SPRINT-1.md) for the roadmap.

## Technology stack

| Layer | Technology |
|---|---|
| Frontend | Next.js 15, React 19, TypeScript, Tailwind CSS v4, shadcn/ui |
| Backend | FastAPI, Python 3.12 |
| Database | SQLite (via SQLAlchemy 2) |
| AI layer | Provider-agnostic Python packages (`ai`, `providers`, `rag`, `vision`) |
| Deployment | Docker, Docker Compose |

## Repository layout

```
openwrt-ai/
├── frontend/          Next.js web UI (no dashboard yet)
├── backend/           FastAPI control plane (app package)
├── ai/                Provider-agnostic AI core: protocols, models, registry
├── providers/         Provider adapters (ollama, nim, openai, openrouter, lmstudio, vllm)
├── rag/               RAG pipeline (chunking / retrieval / reranking)
├── vision/            Vision abstraction + adapters
├── database/          SQLite schema, engine, session, migrations (future)
├── router-agent/      On-device agent (future sprint)
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
- [docs/README.md](docs/README.md) — documentation index

## License

Open-source. TBD.
