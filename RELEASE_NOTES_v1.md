# OpenWrt AI Copilot — v1.0.0 Release Notes

**Version:** 1.0.0

OpenWrt AI Copilot is a self-hostable, provider-independent AI copilot for
managing OpenWrt routers and small fleets. It reads live router state over SSH,
answers natural-language questions grounded in that state, diagnoses
connectivity issues, proposes remediation, and exposes the whole pipeline over a
clean HTTP API with a Next.js UI.

## Highlights

- **Router-aware AI chat.** Ask "what's the CPU load?" or "why is the WAN down?"
  — the assistant answers from the live snapshot and shows the exact router
  context used.
- **Provider independence.** Chat, embeddings, vision, and rerank are
  capability-based abstractions. DeepSeek, OpenAI, OpenRouter, Ollama, and many
  more are swappable via configuration; fully offline / air-gapped operation is
  supported.
- **Encrypted credentials.** Provider API keys and router credentials are
  encrypted at rest and never stored in configuration files or returned by the
  API.
- **OpenWrt management.** Dashboard, system configuration, package management,
  network, firewall, DHCP, DNS, wireless, services, VPN, clients, and system
  logs.
- **Safety by construction.** Every router write is gated by `RouterActionGuard`
  (`allow` / `require_approval` / `deny`).

## What's included

- **Frontend** — Next.js 15 / React 19 / TypeScript: dashboard, AI chat
  (streaming), router management, provider configuration.
- **Backend** — FastAPI control plane with `/chat`, `/chat/stream`,
  `/router/management/*`, `/dashboard/*`, `/providers*`, `/health`, `/ready`.
- **Libraries** — `ai` (core protocols/models), `providers` (adapters),
  `rag` (retrieval), `vision`, `vectorstore`, `knowledge`, `database`.
- **Router Agent** — SSH data collection (ubus/UCI) with pooling and retries.

## Known limitations

- WiFi details are limited to what the router's `ubus` exposes; some boards
  report no radio/station information.
- Chat is grounded in the freshest snapshot; multi-turn conversation memory is
  available in the RAG path.

## Quickstart

```bash
make install          # venv + all Python packages + npm install
make dev-backend      # backend on :8000
make dev-frontend     # frontend on :3000
```

Or run the full stack in Docker:

```bash
docker compose -f docker/docker-compose.yml up --build
```
