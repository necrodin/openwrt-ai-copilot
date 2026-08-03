# OpenWrt AI Copilot — v1.0 Release Notes

**Version:** 0.1.0
**Date:** Sprint 25A

The v1.0 release is a self-hostable, provider-independent AI copilot for
managing OpenWrt router fleets. It reads live router state, answers
natural-language questions grounded in that state, diagnoses connectivity
issues, proposes remediation, and exposes the whole pipeline over a clean HTTP
API with a Next.js UI.

## Highlights

- **Router-aware AI chat.** Ask "what's the CPU load?" or "why is the WAN
  down?" — intent detection automatically selects the relevant router tools,
  the assistant answers from the live snapshot (never hallucinated data), and
  the exact router context used is shown under each reply.
- **Deterministic diagnosis & recommendations.** A health analysis of the
  snapshot (missing WAN, high load, memory pressure, reboots, …) and prioritized
  remediation are produced by deterministic engines and served with the status.
- **Provider independence.** Chat, embeddings, vision, and rerank are
  capability-based abstractions. Ollama, NVIDIA NIM, OpenAI, OpenRouter, LM
  Studio, and vLLM are swappable via a single config file; fully offline /
  air-gapped operation is supported.
- **RAG.** Optional retrieval pipeline over OpenWrt documentation with
  citations, conversation memory, and token budgeting.
- **Safety by construction.** Every router write is gated by
  `RouterActionGuard` (`allow` / `require_approval` / `deny`) — the copilot
  never changes a device autonomously.

## What's included

- **Frontend** — Next.js 15 / React 19 / TypeScript: home, live dashboard
  (WebSocket), AI chat (SSE streaming, router status panel, router-context
  disclosure).
- **Backend** — FastAPI control plane with `/chat`, `/chat/stream`,
  `/chat/history`, `/chat/sessions`, `/router/status`, `/router/info`,
  `/router/context`, `/dashboard/latest`, `/dashboard/ws`, `/providers*`,
  `/health`, `/ready`.
- **Libraries** — `ai` (core protocols/models), `providers` (7 adapters),
  `rag` (retrieval core + AI integration), `vision`, `vectorstore` (SQLite /
  Chroma / Qdrant / FAISS), `knowledge` (ingestion platform), `database`
  (SQLAlchemy engine/session helpers).
- **Router Agent** — data collection over SSH (ubus/UCI) with pooling and
  retries; per-collector failures never abort a pass.
- **Testing** — 730 passing tests (unit + e2e). The e2e suite drives the full
  router pipeline (intent → tool → diagnose → recommend → RAG → cache) against
  a mocked AI transport.
- **Docs** — rewritten `README.md`, `CHANGELOG.md`, sprint documents, and
  `docs/ARCHITECTURE.md`.

## Known limitations

- **No WiFi snapshot yet.** `RouterSnapshot.wifi` is always `None`; the
  diagnosis engine therefore always emits a "Missing WiFi" finding whenever a
  network is present. Wiring a real WiFi collector is future work.
- **Chat is single-turn grounded.** Conversation memory exists in the RAG path;
  the router-aware chat grounds each turn in the freshest snapshot.
- **No authn/authz in v1.** Deploy behind your own reverse proxy if exposed
  beyond a trusted LAN.
- **Config changes are scaffolded, not end-to-end.** `RouterActionGuard`
  implements the safety decision; the apply/rollback pipeline for real UCI
  writes is not yet implemented.

## Upgrade / migration notes

- `GET /router/status` now returns a merged superset contract (legacy
  connection-state fields plus `snapshot`, `diagnosis`, `recommendations`,
  `server_time`). Clients of the legacy shape remain compatible.
- The non-streaming `POST /chat` endpoint still exists, but the frontend only
  uses `POST /chat/stream`. The dead client-side `sendChatMessage` helper was
  removed.
- Dead code removed in 25A (see `CHANGELOG.md`) — no public API surface was
  removed except error classes that were never referenced (`rag.errors.CacheError`,
  `rag.errors.ConfigurationError`, `rag.errors.MemoryError`,
  `knowledge.errors.KnowledgeChunkingError`,
  `knowledge.errors.KnowledgeExtractionError`,
  `router_agent.errors.CollectorError`) and the never-used `vision.Visioner`
  alias (now `VisionProvider`).

## Quickstart

```bash
make install          # venv + all Python packages + npm install
make dev-backend      # backend on :8000
make dev-frontend     # frontend on :3000
make test             # pytest (730 tests)
make lint             # ruff check + format
```

Or run the full stack in Docker:

```bash
docker compose -f docker/docker-compose.yml up --build
```
