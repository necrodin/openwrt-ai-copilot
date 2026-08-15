# OpenWrt AI Copilot

A self-hostable, provider-independent AI copilot for managing OpenWrt routers
and small fleets. Ask questions about your network in natural language, watch
live router state, and manage devices over SSH — all from one web UI.

**Version:** 1.0.0

## Overview

OpenWrt AI Copilot connects to your OpenWrt router over SSH, reads live device
state (system, CPU, memory, storage, network, wireless, services, packages,
logs), and exposes it through a clean web interface and HTTP API. An embedded
AI copilot answers natural-language questions grounded in the live router
state — it never invents data. The AI backend is fully provider-independent:
you bring the model provider you already use, and its API key is stored
encrypted on your own server.

The application is free for personal, non-commercial use under the
[OpenWrt AI Copilot Personal Non-Commercial License](LICENSE).

## Features

- **AI Copilot.** Streaming natural-language chat grounded in the live router
  snapshot, with per-reply router-context disclosure, model selection, and a
  deterministic diagnosis and recommendation engine.
- **Provider-independent AI backend.** Chat, embeddings, vision, and rerank run
  through a capability-based provider abstraction. DeepSeek, OpenAI,
  OpenRouter, Ollama, Anthropic, Gemini, Groq, Together, Mistral, xAI, Cohere,
  Perplexity, Fireworks, Cerebras, Azure OpenAI, NVIDIA NIM, LM Studio, vLLM,
  and any custom OpenAI-compatible endpoint are supported and swappable via
  configuration.
- **OpenWrt router management.** System configuration, time/NTP, firmware
  information, backups, and power actions over SSH.
- **System monitoring.** Live dashboard with CPU, load, memory, storage, network
  interfaces, temperature, and processes, delivered over WebSocket (with REST
  polling fallback).
- **Network diagnostics.** Network interfaces and routing, firewall, DHCP, DNS,
  wireless radios and stations, services, VPN tunnels, connected clients, and
  system logs.
- **Package management.** Installed-package inventory with available upgrades,
  repository feeds, search, and install/remove/upgrade actions (apk and opkg).
- **Security and network information.** Connection state, per-device details,
  and a health-score view of the router.
- **Multi-provider support.** Configure several AI providers side by side, set
  one as the default, and switch per conversation.
- **Model discovery.** Discover a provider's model list from its endpoint using
  the typed or saved credential; manual model entry always remains available.
- **Encrypted API credentials.** Provider API keys and router credentials are
  encrypted at rest and are never written to configuration files, returned by
  the API, or exposed to the browser.
- **Router fleet support.** Save multiple routers, each with its own live
  connection, dashboard, and management surfaces.

## Architecture

The system has three layers:

- **Frontend** — a Next.js 15 / React 19 / TypeScript application: dashboard,
  AI chat (streaming), router management, and provider configuration. It talks
  to the backend over the HTTP API and a WebSocket dashboard stream.
- **Backend** — a FastAPI control plane that handles authentication, the live
  dashboard, the AI chat pipeline, provider configuration, and router
  management over SSH. Router writes are gated by a safety policy
  (`allow` / `require_approval` / `deny`).
- **Libraries and router agent** — provider-agnostic Python packages
  (`ai`, `providers`, `rag`, `vision`, `vectorstore`, `knowledge`, `database`)
  and an SSH-based router agent (`ubus`/`UCI`) that collects device state with
  pooling and retries.

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full description.

## Requirements

Tested on:

- **Backend host** — Python 3.12+ on Linux or macOS.
- **Frontend build** — Node.js 20+.
- **Router** — OpenWrt with SSH (dropbear/OpenSSH) enabled and root access.
  Verified against OpenWrt 25.12 (apk package manager) and OpenWrt 22/23
  (opkg); SSH access over the LAN is sufficient.

## Quick Start

### Backend

```bash
make install        # create .venv, install Python packages, install frontend deps
make dev-backend    # uvicorn on http://localhost:8000
```

### Frontend

```bash
make dev-frontend   # Next.js dev server on http://localhost:3000
```

Open http://localhost:3000 and complete the first-run setup (create the admin
account), then add your router and AI provider.

### Development

```bash
make test           # pytest (tests/)
make lint           # ruff check + format check
make format         # ruff format
cd frontend && npm run lint && npx tsc --noEmit   # frontend lint + types
cd frontend && node --test tests/*.test.mjs       # frontend tests
```

### Docker

```bash
docker compose -f docker/docker-compose.yml up --build
```

- Frontend: http://localhost:3000
- Backend API docs: http://localhost:8000/api/docs

## OpenWrt Setup

1. On the router, enable SSH and set a root password (or install an SSH key).
2. From the application, add the router by IP/hostname, port, username, and
   password or key.
3. The backend connects over SSH and reads state via `ubus` and `uci`. Only the
   credentials you provide are used; router passwords and private keys are
   encrypted at rest.

## AI Providers

Each AI provider is configured with:

- **Provider type** — DeepSeek, OpenAI, OpenRouter, Ollama, a custom
  OpenAI-compatible endpoint, and many others.
- **Endpoint (base URL)** — pre-filled with the provider's default; custom
  endpoints can use any OpenAI-compatible URL.
- **API key** — entered once. It is encrypted server-side and never written to
  `providers.yaml`, returned by the API, or shown in the UI. Editing a provider
  with an empty key field keeps the existing credential; entering a new key
  replaces it.
- **Model** — chosen manually or discovered from the endpoint (model discovery
  uses the typed key, or the saved credential when editing with an empty key
  field).
- **Connection test** — verifies the exact configured endpoint, credential, and
  model with a real streaming completion before you save.

## Configuration

Runtime configuration is done through the web UI (Settings → AI Providers and
router onboarding). Advanced settings are read from environment variables and
`.env` files:

- `PROVIDER_CONFIG_FILE` — provider configuration file (default `providers.yaml`).
- `DATABASE_URL` — SQLite database path.
- `AUTH_ADMIN_API_KEY` / `AUTH_READONLY_API_KEY` — programmatic API keys.
- `AUTH_VAULT_KEY` — encryption key for the credential vault (auto-generated
  and persisted when not set).
- `ROUTER_DEVICE_HOST` / `ROUTER_DEVICE_PORT` / `ROUTER_USERNAME` /
  `ROUTER_SSH_KEY` / `ROUTER_PASSWORD` — default router connection.

See `frontend/.env.example` and `backend/app/core/config.py` for the full list.

## API

The public API lives under `/api/v1` (interactive docs at `/api/docs`).

| Endpoint | Description |
|---|---|
| `GET /api/v1/health` | Liveness probe (`status`, `service`, `version`, `environment`) |
| `GET /api/v1/ready` | Readiness probe |
| `POST /api/v1/auth/login` | Browser session login |
| `GET /api/v1/dashboard/latest` | Latest dashboard update |
| `WS /api/v1/dashboard/ws` | Live dashboard stream |
| `POST /api/v1/chat/stream` | Streaming AI reply over Server-Sent Events |
| `GET /api/v1/chat/sessions` | Chat sessions |
| `GET /api/v1/router/management/system` | System configuration snapshot |
| `GET /api/v1/router/management/packages` | Installed packages and upgrades |
| `GET /api/v1/router/management/packages/search` | Repository package search |
| `GET /api/v1/providers` | Configured AI providers |
| `GET /api/v1/providers/types` | Supported provider types |
| `POST /api/v1/providers` | Add a provider |
| `POST /api/v1/providers/discover-models` | Discover models for a draft provider |
| `POST /api/v1/providers/test` | Test a draft provider configuration |
| `GET /api/v1/setup/status` | First-run setup state |

## Security

- **Provider API keys** are encrypted (Fernet, AES-128-CBC + HMAC-SHA256) into
  `provider_credentials.json` and are never stored in `providers.yaml`, never
  logged, and never returned by the API. The web UI only ever sees a boolean
  `has_credential`.
- **Router credentials** (password / SSH key) are encrypted at rest in a
  server-side credential vault and are never returned by the API.
- **Authentication** uses server-side browser sessions with role-scoped
  permissions (admin / read-only), plus optional programmatic API keys.
- **Router safety** — every router write is gated by the `RouterActionGuard`
  policy; the copilot never changes a device without the configured approval
  rules.

## Troubleshooting

- **Router unreachable in the dashboard.** Verify SSH is enabled on the router
  and that the backend host can reach the router's SSH port. Check the
  connection badge on the System page.
- **Package repository search says the index is unavailable.** Run "Update
  feeds" on the Packages page (the app also auto-refreshes a missing index on
  search). Confirm the router can reach its configured package feeds.
- **Provider connection test fails.** Confirm the base URL, API key, and model
  are correct for the provider type. The test distinguishes endpoint, auth,
  model, and rate-limit failures.
- **System values show N/A.** Some fields are not reported by every router/board;
  N/A means the router did not provide that value.

## Roadmap

Planned future work:

- Deeper WiFi snapshot collection across more hardware.
- Additional router management actions behind the existing approval policy.
- Multi-turn conversational memory in the router-aware chat.
- Support for more OpenWrt releases and package managers.

## License

This software is provided under the **OpenWrt AI Copilot Personal
Non-Commercial License**. Personal, private, non-commercial use is permitted;
commercial use, resale, and offering the software as a paid service are
prohibited. See [LICENSE](LICENSE) for the full terms.

## Documentation

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — system architecture
- [docs/FEATURE_ROUTER_ONBOARDING.md](docs/FEATURE_ROUTER_ONBOARDING.md) — router onboarding
- [docs/README.md](docs/README.md) — documentation index
- [CHANGELOG.md](CHANGELOG.md) — release history
- [RELEASE_NOTES_v1.md](RELEASE_NOTES_v1.md) — v1.0.0 release notes
