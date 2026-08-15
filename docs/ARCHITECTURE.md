# OpenWrt AI Copilot — System Architecture

> Status: Implemented
> Version: 1.0.0

This document describes the architecture of the implemented system: a
self-hostable, provider-independent AI copilot for managing OpenWrt routers.

## Overview

The application has three layers:

1. **Frontend** — a Next.js 15 / React 19 / TypeScript web application.
2. **Backend** — a FastAPI control plane (`backend/app`).
3. **Libraries and router agent** — provider-agnostic Python packages and an
   SSH-based router agent.

The backend connects to the router over SSH, collects live device state via
`ubus`/`uci`, and serves it to the frontend over a REST API and a WebSocket
dashboard stream. An AI chat pipeline answers natural-language questions
grounded in the live snapshot. All AI calls go through a provider-independent
abstraction, so the model provider is a configuration choice, not a code
dependency.

## Components

### Frontend (`frontend/`)

Next.js 15 + React 19 + TypeScript + Tailwind CSS. It provides:

- Dashboard with live router state (CPU, load, memory, storage, network).
- AI chat with streaming replies and router-context disclosure.
- Router management surfaces: System, Packages, Network, Security, Monitoring.
- Provider configuration (Settings → AI Providers).
- Authentication (login / first-run setup) and role-aware UI.

The frontend communicates with the backend over `/api/v1` and subscribes to the
dashboard WebSocket stream (with a REST polling fallback).

### Backend (`backend/app/`)

FastAPI application with the following routers under `/api/v1`:

- `auth.py` — browser sessions (server-side store) and setup.
- `chat.py` — streaming and non-streaming chat, sessions, history.
- `dashboard.py` — `GET /dashboard/latest` and `WS /dashboard/ws`.
- `providers.py` — provider CRUD, model discovery, connection testing.
- `management.py` — router management (system, packages, storage, services, …).
- `onboarding.py` — router save/list/delete and connection probing.
- `router_status.py`, `router.py` — router status and info.
- `health.py` — `/health`, `/ready`.

Key services:

- `provider_manager.py` — builds the provider manager from `providers.yaml`.
- `provider_credentials.py` — encrypted store for provider API keys.
- `snapshot_service.py` — polls the router and serves dashboard updates.
- `router_management.py` — SSH-based router management operations.
- `chat_service.py` — the chat pipeline.

### Provider layer (`providers/`, `ai/`)

Providers are configured through `providers.yaml` and instantiated by the
provider factory. Every adapter implements the capability-based protocols from
`ai.core` (chat, embeddings, vision, rerank). Supported types include DeepSeek,
OpenAI, OpenRouter, Ollama, Anthropic, Gemini, Groq, and any custom
OpenAI-compatible endpoint.

API keys are never stored in the configuration file. They are encrypted
(Fernet) into `provider_credentials.json` by the credential store, resolved
server-side when a provider is built, and exposed to the API only as a boolean
`has_credential`.

### Router agent (`router-agent/`)

Collects device state over SSH via `ubus`/`uci`. Each collector reports
independently with pooling and retries; a failed collector never aborts a
collection pass. The backend's `RouterManagementService` runs management
operations (system settings, packages, backups, power) over the same SSH
connection.

## Authentication and security

- Browser users authenticate with a username/password against a bcrypt-hashed
  account store; sessions are held server-side and can be revoked.
- Programmatic clients authenticate with `AUTH_ADMIN_API_KEY` /
  `AUTH_READONLY_API_KEY` (Bearer).
- Roles are `admin` (full access including management/write actions) and
  `read-only`.
- Router credentials and provider API keys are encrypted at rest with a Fernet
  vault (`AUTH_VAULT_KEY`, or a persisted key file). They are never returned by
  the API.
- Router writes are gated by the `RouterActionGuard` policy
  (`allow` / `require_approval` / `deny`).

## Data flow

1. The frontend loads and authenticates (session or API key).
2. The snapshot service connects to the saved router over SSH and polls device
   state on an interval; updates are streamed to the dashboard via WebSocket.
3. The user asks the Copilot a question. The chat pipeline builds a prompt
   grounded in the latest snapshot, calls the configured provider's streaming
   chat endpoint, and streams the reply back.
4. Management actions (system config, package operations, …) run over SSH and
   are recorded as management jobs.

## Deployment

- Development: `make dev-backend` (uvicorn, :8000) and `make dev-frontend`
  (Next.js, :3000).
- Docker: `docker compose -f docker/docker-compose.yml up --build`.
- Storage: SQLite (via SQLAlchemy) for application data; encrypted credential
  files live next to the provider configuration.
