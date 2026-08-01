# OpenWrt AI Copilot — System Architecture

> Status: **Approved — Sprint 1 revisions applied**
> Version: 0.1
> Author: Principal Software Architect

---

## Sprint 1 revisions (supersede earlier stack assumptions)

The Sprint 1 stack decision overrides the Go/Postgres/Qdrant/NATS choices in
§14–§16 where they conflict:

| Area | Earlier assumption | Approved for implementation |
|---|---|---|
| Backend | Go microservices | **FastAPI + Python 3.12** (one `backend/app` package; microservices become Python services later) |
| Frontend | Vue 3 | **Next.js 15 + React 19 + TypeScript + Tailwind v4 + shadcn/ui** |
| Database | Postgres + Qdrant | **SQLite (SQLAlchemy 2)** for Sprint 1; Postgres/Qdrant remain later-phase options |
| Provider layer | Go `pkg/` | Python packages: `ai/` (contracts), `providers/` (adapters), `rag/`, `vision/` |
| Router agent | Go | Python package `router_agent/` (scaffold only) |
| Event bus | NATS JetStream | Deferred (not needed for Sprint 1 foundation) |

The provider-agnostic abstractions (§6–§9), the capability model, and the
safety pipeline (§13.5) are **unchanged** in spirit and are implemented as the
`ai.core` protocols and `providers` package structure.

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Design Principles](#2-design-principles)
3. [Overall Architecture](#3-overall-architecture)
4. [Folder Structure](#4-folder-structure)
5. [Microservices](#5-microservices)
6. [AI Provider Abstraction](#6-ai-provider-abstraction)
7. [Embedding Abstraction](#7-embedding-abstraction)
8. [Vision Abstraction](#8-vision-abstraction)
9. [Reranker Abstraction](#9-reranker-abstraction)
10. [Database Schema](#10-database-schema)
11. [API Specification](#11-api-specification)
12. [Sequence Diagrams](#12-sequence-diagrams)
13. [Security Model](#13-security-model)
14. [Deployment Model](#14-deployment-model)
15. [Docker Architecture](#15-docker-architecture)
16. [Decision Log](#16-decision-log)
17. [Open Questions for Approval](#17-open-questions-for-approval)

---

## 1. Executive Summary

**OpenWrt AI Copilot** is a self-hostable, production-grade AI assistant for
managing OpenWrt router fleets. It answers natural-language questions about the
network, diagnoses connectivity/security issues, explains logs, and — under
strict human approval — proposes and applies validated configuration changes.

### Hard constraints

1. **No dependency on any single AI provider.**
2. **The AI layer is fully provider-independent.** Core code never imports a
   provider SDK; all inference flows through pluggable adapters.
3. Supported providers: **Ollama, NVIDIA NIM, OpenAI, OpenRouter, LM Studio,
   vLLM**. Every provider is optional and dynamically interchangeable.
4. Must be able to run **100% offline / air-gapped** with only local providers.

### What this architecture covers

- A control plane of small, independently deployable microservices.
- A lightweight **on-router agent** for fleet management (the heavy AI runs off-device).
- Provider-agnostic abstractions for **chat, embeddings, vision, and reranking**.
- **RAG** over OpenWrt documentation, UCI schemas, device configs, and logs.
- A strict **safety model** around mutating router configuration.

### Non-goals (v1)

- Replacing the OpenWrt/LuCI web UI.
- Running heavy LLM inference *on* the router itself (a small local model may be
  offered later as an experimental profile).
- Training/fine-tuning models.

---

## 2. Design Principles

| Principle | Implication |
|---|---|
| **Provider independence** | Core never imports an AI SDK. All provider interaction goes through the Provider Gateway. Swapping Ollama → OpenAI is a config change, not a code change. |
| **Capability-based abstraction** | Providers are modeled as capabilities (chat, embed, vision, rerank), not as a single monolithic interface. A provider may implement any subset. |
| **Local-first / privacy-preserving** | All data and inference can stay on-premises. Cloud providers are opt-in. |
| **Safety by construction** | Device mutations require dry-run → validation → approval → apply → snapshot → rollback. Copilot can never change a device autonomously. |
| **Observability & audit** | Every AI call, tool invocation, and device operation is traced, logged, and cost-accounted. |
| **Golang everywhere** | One language across the control plane and the router agent; single static binaries, trivial cross-compilation to router architectures. |
| **Standard protocols** | Where a provider speaks OpenAI-compatible HTTP, we use it; native endpoints are wrapped by adapters. |
| **Everything is a data plane over an event bus** | Services communicate via gRPC for request/response and a NATS JetStream bus for events. |

---

## 3. Overall Architecture

```
                       ┌─────────────────────────────────────────────┐
                       │               CLIENTS                        │
                       │  Web UI · LuCI Plugin · CLI · MCP Client     │
                       └──────────────────────┬──────────────────────┘
                                              │ HTTPS (OIDC / JWT)
                                              ▼
                                   ┌───────────────────┐
                                   │    API GATEWAY     │
                                   │ auth · rbac · tls │
                                   │ ratelimit · sse    │
                                   └─────────┬─────────┘
                                             │ gRPC (mTLS)
          ┌────────────────┬─────────────────┼────────────────┬─────────────────┐
          ▼                ▼                 ▼                ▼                 ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │  COPILOT     │ │   DEVICE     │ │  KNOWLEDGE   │ │    AUTH      │ │   POLICY &   │
  │   ENGINE     │ │ CONTROLLER   │ │   SERVICE    │ │   SERVICE    │ │  GUARDRAILS  │
  │ orchestration│ │  fleet mgmt  │ │    RAG       │ │ identity/keys│ │  safety/audit│
  └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
         │                │                │                │                │
         ▼                ▼                ▼                ▼                ▼
  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
  │  PROVIDER    │ │  TELEMETRY   │ │  QDRANT      │ │  POSTGRES    │ │  NATS        │
  │  GATEWAY     │ │  SERVICE     │ │  vector DB   │ │  relational  │ │  JetStream   │
  │  (AI Router) │ │  metrics/logs│ │              │ │              │ │  event bus   │
  └──────┬───────┘ └──────┬───────┘ └──────────────┘ └──────────────┘ └──────────────┘
         │                │
         │                │  MQTT / agent push
         ▼                ▼
  ┌────────────────────────────┐   ┌──────────────────────────┐
  │   MODEL PLANE (optional)   │   │      EDGE PLANE          │
  │  Ollama · NIM · vLLM ·     │   │   OpenWrt Router(s)      │
  │  LM Studio · OpenAI ·      │   │   ┌──────────────────┐   │
  │  OpenRouter (cloud)        │   │   │  Router Agent    │   │
  └────────────────────────────┘   │   │  (ubus/UCI,      │   │
                                   │   │   probes, apply) │   │
                                   │   └──────────────────┘   │
                                   └──────────────────────────┘
```

### Trust domains

- **Edge plane** — the routers themselves; the most hostile/least trusted.
- **Model plane** — AI model servers (local or cloud). Only the Provider Gateway
  talks to it.
- **Control plane** — the microservices; internal traffic is mTLS.
- **Client plane** — browsers, CLI, MCP clients; authenticated at the gateway.

---

## 4. Folder Structure

Monorepo, Go services, one module per service. Shared, provider-agnostic logic
lives in `pkg/` and is imported by services (never the other way around).

```
openwrt-ai/
├── api/
│   ├── openapi/                 # Public REST specs (OpenAPI 3.1)
│   │   └── v1.yaml
│   ├── proto/                   # Internal gRPC contracts
│   │   ├── engine.proto
│   │   ├── provider.proto
│   │   ├── knowledge.proto
│   │   ├── device.proto
│   │   ├── policy.proto
│   │   └── telemetry.proto
│   └── buf.yaml
│
├── services/
│   ├── gateway/                 # API Gateway
│   │   ├── cmd/gateway/
│   │   └── internal/...
│   ├── engine/                  # Copilot Engine (orchestrator)
│   ├── provider-gateway/        # AI Router / provider abstraction
│   ├── knowledge/               # RAG service
│   ├── device-controller/       # Fleet management + safe execution
│   ├── telemetry/               # Metrics/log ingest + anomaly detection
│   ├── policy/                  # Guardrails, filtering, audit
│   └── auth/                    # Identity, API keys, credential vault
│
├── pkg/                          # Shared libraries (provider-agnostic)
│   ├── aiprovider/              # Provider interfaces + capability registry
│   │   ├── chat/                # Completion/chat interface
│   │   ├── embedding/           # Embedder interface
│   │   ├── vision/              # Visioner interface
│   │   └── reranker/            # Reranker interface
│   ├── adapters/                # Provider adapter implementations
│   │   ├── openaicompat/        # Shared OpenAI-compatible core
│   │   ├── ollama/              # Native Ollama adapter
│   │   ├── nim/                 # NVIDIA NIM adapter
│   │   ├── vllm/                # vLLM adapter (OpenAI-compatible)
│   │   ├── lmstudio/            # LM Studio adapter
│   │   └── openrouter/          # OpenRouter adapter
│   ├── uci/                     # UCI config parse/validate/diff/rollback
│   ├── device/                  # Device model, transports (ssh/ubus/ws)
│   ├── telemetry/               # Metric/log ingestion types
│   ├── security/                # crypto, redaction, vault client
│   ├── observability/           # OTEL, logging, tracing helpers
│   └── bus/                     # NATS client wrappers, event schema
│
├── agent/                        # On-router OpenWrt agent (Go, static binary)
│   ├── cmd/agent/
│   └── internal/...              # ubus client, UCI, probe runner, TLS client
│
├── ui/                           # Web UI (Vue 3 + TypeScript + Vite)
├── deploy/
│   ├── compose/                  # docker-compose topologies
│   │   ├── all-in-one.yaml
│   │   ├── offline.yaml          # local models only
│   │   └── hybrid.yaml
│   ├── k8s/                      # Helm chart + kustomize overlays
│   ├── docker/                   # Dockerfiles per service
│   └── openwrt/                  # opkg package for the router agent
│
├── docs/
│   ├── architecture/             # ADRs, sequence docs
│   └── guide/                    # User/admin docs
├── tests/
│   ├── integration/
│   ├── contract/                 # Adapter conformance tests
│   └── e2e/
├── Makefile
├── go.work
└── README.md
```

---

## 5. Microservices

All services are Go, stateless where possible, state owned by Postgres/Qdrant.

### 5.1 API Gateway (`services/gateway`)
- Single public entry point. Terminates TLS, verifies OIDC/JWT, enforces RBAC
  and scopes, applies rate limiting, validates requests, and reverse-proxies to
  internal gRPC endpoints.
- Translates REST ↔ gRPC; proxies SSE/WebSocket streaming from the Engine.
- Never holds business logic or secrets (only short-lived session tokens).

### 5.2 Copilot Engine (`services/engine`)
The "brain". Responsibilities:
- Conversation state machine (sessions, memory, context window management).
- **Tool-calling orchestration**: decides when to call device diagnostics, RAG
  search, or config tools; loop with the Provider Gateway until final answer.
- RAG orchestration: builds queries → Knowledge Service → rerank → context.
- Persona/system-prompt assembly with a **provider-agnostic prompt template**
  (markers substituted per provider capabilities, e.g. tool format).
- Streaming to clients over SSE/WebSocket.
- Persists conversations/messages/tool calls to Postgres.

### 5.3 Provider Gateway — "AI Router" (`services/provider-gateway`)
The heart of provider independence. Responsibilities:
- Exposes unified gRPC/REST APIs for **chat, embeddings, vision, rerank**.
- Maintains the **capability registry**: which provider supports what, and a
  normalized **model catalog**.
- **Adapter dispatch**: routes a request to the right adapter based on routing
  rules (model → provider; fallback chains; cost/latency-aware routing).
- Reliability: timeouts, retries with jitter, circuit breakers, **failover**
  across providers for the same logical model.
- **Token & cost accounting**: every call is metered and emitted as an event.
- Health checks + capability probing on startup and periodically.

### 5.4 Knowledge Service (`services/knowledge`)
RAG pipeline control plane:
- Ingestion pipeline: document loaders (OpenWrt docs, wiki, UCI schemas, device
  config snapshots, logs), chunking strategies (semantic + fixed-size),
  embedding via the Provider Gateway, upsert into Qdrant.
- Retrieval: hybrid search (dense + BM25 sparse via Qdrant), then **reranking**
  via the Provider Gateway, then context assembly.
- Manages knowledge bases, per-tenant isolation, and freshness/rebuild jobs.

### 5.5 Device Controller (`services/device-controller`)
Fleet management and **safe execution** of operations:
- Manages router connections (direct SSH, or a reverse tunnel from the router
  agent). Sends commands, receives telemetry.
- Abstraction over `ubus`, UCI, and shell for OpenWrt.
- Runs **diagnostics**: ping, traceroute, DNS lookup, DHCP/lease inspection,
  interface/bandwidth stats, log tailing.
- Implements the **config-change safety pipeline**: template → dry-run →
  UCI-validation → semantic validation → apply → snapshot → health check →
  rollback.
- All mutating operations are queued, permission-checked, and approved.

### 5.6 Telemetry Service (`services/telemetry`)
- Ingests metrics/logs/events pushed by router agents or pulled via MQTT.
- Short-term anomaly detection (e.g., interface flapping, high error rates,
  sudden reboot) → emits domain events → the Engine can surface these to the
  user proactively.
- Feeds a rolling window of recent logs into Qdrant for "explain this log"
  queries.

### 5.7 Policy & Guardrails Service (`services/policy`)
- **Input/output filtering**: prompt-injection detectors, PII/sensitive data
  redaction on outputs.
- **Instruction hierarchy**: distinguishes system vs user vs tool instructions;
  refuses tool results that try to re-instruct the model.
- **Device-operation authorization**: every mutating tool call is validated
  against user permissions and safety rules (e.g., "never change the WAN if it
  is the only uplink", "require admin scope").
- Emits **audit events** (tamper-evident, signed).
- Policy-as-code: rules live in versioned YAML/Rego bundles.

### 5.8 Auth Service (`services/auth`)
- OIDC identity provider + external IdP federation (e.g., Authentik, Keycloak).
- Users, tenants, roles, scopes; JWT + API keys.
- **Provider credential vault**: encrypts and stores API keys for the six
  providers; the Provider Gateway obtains credentials here at request time
  (never stored in its own config).
- Key rotation, secrets access logging.

### 5.9 Router Agent (`agent/` — edge)
- Tiny Go daemon installed on each OpenWrt router (static musl binary,
  cross-compiled for mipsle/aarch64/arm).
- Reads UCI, subscribes to `ubus`, exposes metrics, executes *authorized*
  commands.
- Maintains an outbound secure channel (WebSocket over TLS) to the Device
  Controller — no inbound ports needed on the router.
- Enforces a local allowlist of executable commands; everything else is refused.

### Supporting infrastructure
- **NATS JetStream** — internal event bus (audit, telemetry, task queues,
  device events).
- **Postgres** — system of record.
- **Qdrant** — vector store (dense + sparse).
- **Redis** — caching (session state, rate-limit counters, model catalog) and
  pub/sub fan-out for SSE.
- **OTel Collector + Prometheus + Grafana** — observability.

---

## 6. AI Provider Abstraction

### 6.1 Design
Providers are modeled as **capabilities**. A provider implements any subset of:

```go
// chat/completion
type Completer interface {
    Chat(ctx context.Context, req ChatRequest, stream func(Chunk)) (ChatResponse, error)
    Models(ctx context.Context) ([]Model, error)
}

// embedding
type Embedder interface {
    Dimensions() int
    Embed(ctx context.Context, texts []string) ([]Embedding, error)
}

// vision (multimodal) — see §8
type Visioner interface {
    Describe(ctx context.Context, req VisionRequest) (VisionResponse, error)
}

// rerank — see §9
type Reranker interface {
    Rerank(ctx context.Context, query string, docs []string, topN int) ([]ScoredDoc, error)
}
```

- The Provider Gateway exposes these capabilities **upstream** as unified gRPC
  APIs. Everything downstream (Engine, Knowledge, Policy) sees only the unified
  API — never a provider type.
- A **capability registry** maps `(capability, model)` → adapter + config.
  Startup probing detects which endpoints work and their feature flags
  (streaming, tool-calling, vision, embeddings, JSON mode).
- **Model catalog** normalizes names. A logical model like `coder-qwen-7b` maps
  to one or more concrete providers (`ollama:qwen2.5-coder:7b`,
  `openai:gpt-5-mini`) with routing rules and fallback order.

### 6.2 Adapter strategy
Most providers (OpenAI, OpenRouter, vLLM, LM Studio, NIM, and Ollama's compat
mode) speak **OpenAI-compatible HTTP**. So:

- A shared `openaicompat` core implements chat/embed/vision against `/v1/*`
  once, with per-provider differences reduced to config:
  - `base_url`, `api_key_ref`, auth header style, model name mapping,
    extra headers (e.g. OpenRouter `HTTP-Referer`).
- Thin native adapters exist only where the native API adds value:
  - **Ollama**: native `/api/chat`, `/api/embed` (used for prompt formats,
    `keep_alive`, and `num_ctx` tuning); can also use compat mode.
  - **NIM**: OpenAI-compatible chat/embed, plus dedicated **rerank** endpoint.
- Streaming is standardized to an event envelope (delta text / tool-call
  fragments / done) so downstream code never sees provider-specific framing.

### 6.3 Provider capability matrix (target)

| Capability | Ollama | NIM | OpenAI | OpenRouter | LM Studio | vLLM |
|---|---|---|---|---|---|---|
| Chat | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Streaming | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Tool calling | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Embeddings | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Vision | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| Rerank | local c-e | ✓ | — | — | — | — |

Rerank is covered by a local cross-encoder adapter + NIM; absent providers are
handled via fallback routing.

### 6.4 Routing rules
```yaml
# routing_rules.yaml (versioned, hot-reloadable)
catalog:
  - logical: "general-embed"
    strategy: failover
    targets:
      - provider: ollama,      model: "bge-m3",       cost: 0,   priority: 1
      - provider: nim,         model: "NV-Embed-QA",  cost: 0.3, priority: 2
  - logical: "coder-chat"
    strategy: cheapest_first   # or latency_first, pinned
    targets:
      - provider: vllm,        model: "Qwen/Qwen2.5-Coder-7B", priority: 1
      - provider: openrouter,  model: "qwen/qwen2.5-coder-7b-instruct", priority: 2
```

---

## 7. Embedding Abstraction

### 7.1 Interface
```go
type Embedder interface {
    ID() string
    Dimensions() int
    Embed(ctx context.Context, texts []string) ([]Embedding, error) // batch, dim-normalized
}
```

### 7.2 Semantics
- All embeddings are **normalized** and stored with their dimension + distance
  metric so the same Qdrant collection can be migrated safely.
- The Knowledge Service records `(embedder_id, dimensions, model)` per chunk —
  retrieval only ever queries chunks produced by the same embedder.
- **Batching** is handled upstream (respecting provider batch limits).

### 7.3 Adapters
| Adapter | Typical model | Notes |
|---|---|---|
| `ollama` | `bge-m3`, `nomic-embed-text` | native `/api/embed` |
| `nim` | `NV-Embed-QA-Mistral-4B` | OpenAI-compat `/v1/embeddings` |
| `openai` | `text-embedding-3-large` | dimensions configurable |
| `vllm` | `BAAI/bge-m3`, `nomic-ai/nomic-embed-text` | OpenAI-compat server |
| `lmstudio` | `bge-m3`, `nomic` | OpenAI-compat server |
| `openrouter` | any hosted embed model | routed |
| `local-onnx` (built-in) | `all-MiniLM-L6-v2` | offline fallback, no external runtime |

### 7.4 Cost/latency routing
Embedding requests are routed per the `general-embed` rule; local adapters are
preferred unless a policy/quality rule requires otherwise. Failover: any error →
next adapter in the chain.

---

## 8. Vision Abstraction

### 8.1 Rationale
Vision is treated as **multimodal chat**: content blocks of type `text` and
`image` are passed to a model that supports image input. This lets us reuse the
chat path, streaming, and routing rather than inventing a parallel API.

### 8.2 Interface
```go
type Visioner interface {
    Describe(ctx context.Context, req VisionRequest) (VisionResponse, error)
}

type VisionRequest struct {
    Model    string        // logical model, e.g. "vision-general"
    Prompt   string
    Images   []ImageRef    // { Data []byte | URL string, MimeType string }
    Options  VisionOptions // detail level, max_tokens, temperature
}
```

### 8.3 Content-block model
The unified `ChatRequest` uses typed parts:
```go
type Part struct {
    Kind  PartKind // Text | Image
    Text  string
    Image *ImageRef
}
```
Each adapter maps `Image` parts to its native format:
- OpenAI/OpenRouter: `image_url` content parts (data URI or hosted URL).
- Ollama: base64 images with `images: [...]`.
- vLLM/NIM/LM Studio: OpenAI-compatible `image_url`.

### 8.4 Uses in OpenWrt AI Copilot
- Interpreting **network topology / diagram** uploads.
- Reading **Wi-Fi heatmap** or **router status screenshots**.
- Validating **QR codes / provisioning tokens** during onboarding.
- OCR of vendor error dialogs pasted as images.

### 8.5 Default behavior
`vision-general` routes to the first configured provider whose capability probe
reports `vision: true`. If none, the Engine returns a graceful "no vision model
configured" response (capability-aware degradation).

---

## 9. Reranker Abstraction

### 9.1 Interface
```go
type Reranker interface {
    Rerank(ctx context.Context, query string, docs []string, topN int) ([]ScoredDoc, error)
}
```

### 9.2 Where it fits
Knowledge Service retrieves a wide candidate set (e.g., 50 chunks) → calls the
Provider Gateway rerank API → keeps top-N (e.g., 8) for context. Reranking is
**optional**: if no reranker is configured, retrieval returns the top-N by raw
score.

### 9.3 Adapters
| Adapter | Model | Notes |
|---|---|---|
| `local-cross-encoder` (built-in) | `bge-reranker-base` ONNX | offline, runs in-process |
| `nim` | `nv-rerank-qa-mistral-4b` | remote rerank endpoint |
| `opentelemetry-counted` | — | wrapper that meters every rerank |

Rerank quality is stored per retrieval so RAG effectiveness can be measured.

---

## 10. Database Schema

### 10.1 Postgres (system of record)

```sql
-- Identity & tenancy
tenants            (id uuid pk, name text, slug text unique, plan text,
                     created_at timestamptz)
users              (id uuid pk, tenant_id fk, email text, name text,
                     password_hash bytea null, oidc_sub text null, status text)
roles              (id uuid pk, tenant_id fk, name text, scope text[])  -- scope: e.g. devices.read, devices.write, ai.chat
user_roles         (user_id fk, role_id fk, pk(user_id, role_id))
api_keys           (id uuid pk, tenant_id fk, user_id fk null, name text,
                     key_hash bytea, scopes text[], expires_at, revoked_at,
                     last_used_at)

-- Provider credentials (encrypted)
providers          (id uuid pk, tenant_id fk, type text,        -- ollama|nim|openai|openrouter|lmstudio|vllm
                     name text, base_url text, model_prefix text,
                     enabled bool, priority int)
provider_creds     (id uuid pk, provider_id fk unique, encrypted_secret bytea,
                     kms_key_id text, algorithm text, rotation_policy text,
                     updated_at)
model_catalog      (id uuid pk, tenant_id fk, logical_name text, provider_id fk,
                     provider_model text, capability text[], cost_per_1k_in text,
                     cost_per_1k_out numeric, priority int, enabled bool)

-- Conversations
conversations      (id uuid pk, tenant_id fk, user_id fk, title text,
                     device_ids uuid[] null, status text, created_at, updated_at)
messages           (id uuid pk, conversation_id fk, role text, -- system|user|assistant|tool
                     parts jsonb,                 -- text/image/tool parts
                     model text null, provider_id fk null,
                     prompt_tokens int, completion_tokens int,
                     tool_call_id text null, created_at)
tool_calls         (id uuid pk, message_id fk, tool_name text,
                     arguments jsonb, status text, result jsonb, error text,
                     latency_ms int, created_at)

-- Devices
devices            (id uuid pk, tenant_id fk, name text, hostname text,
                     model text, firmware text, arch text,
                     agent_connected bool, last_seen_at,
                     wan_ip text, wan_status text, uptime_s int,
                     tags jsonb)
device_groups      (id uuid pk, tenant_id fk, name text, filter jsonb)
device_snapshots   (id uuid pk, device_id fk, label text, uci_config jsonb,
                     config_hash text, created_by uuid, created_at)
device_tasks       (id uuid pk, device_id fk, task_type text, -- diagnostic|apply|rollback|probe
                     params jsonb, status text, progress int,
                     approval_state text,            -- pending|approved|rejected|auto
                     approved_by uuid null, plan jsonb null,
                     snapshot_before uuid fk null, snapshot_after uuid fk null,
                     result jsonb, error text, created_at, updated_at)

-- Knowledge
knowledge_bases    (id uuid pk, tenant_id fk, name text, type text, -- docs|uci|logs|device_corpus
                     embedder_id text, dimension int, created_at)
documents          (id uuid pk, kb_id fk, source_uri text, source_type text,
                     content_type text, title text, checksum text,
                     status text, chunk_count int, created_at, updated_at)
chunks             (id uuid pk, document_id fk, kb_id fk, index int,
                     text text, metadata jsonb, vector_id text,  -- qdrant point id
                     embedder_id text, created_at)

-- Usage & cost
usage_events       (id bigserial pk, tenant_id fk, capability text, provider_id fk,
                     logical_model text, prompt_tokens int, completion_tokens int,
                     cost_usd numeric(12,6), latency_ms int, ok bool,
                     started_at timestamptz)

-- Audit
audit_events       (id bigserial pk, tenant_id fk, actor_type text, actor_id text,
                     action text, resource_type text, resource_id text,
                     before jsonb null, after jsonb null,
                     ip text null, request_id text, signature bytea,  -- tamper-evident
                     created_at)
```

### 10.2 Qdrant (vectors)

| Collection | Payload | Distance | Notes |
|---|---|---|---|
| `knowledge_chunks` | `tenant_id, kb_id, document_id, chunk_index, text, embedder_id, dimension` | Cosine | dense + sparse (hybrid) |
| `telemetry_events` | `tenant_id, device_id, ts, severity, source, summary` | Cosine | rolling window for log RAG |
| `device_corpus` | `tenant_id, device_id, kind (config|status|snapshot)` | Cosine | per-device searchable state |

### 10.3 Redis
- Session cache, rate-limit counters, cached model catalog, SSE fan-out.

---

## 11. API Specification

### 11.1 Public REST (via API Gateway) — OpenAPI 3.1

**Chat & models**
```
POST /v1/chat/completions      # streaming SSE; OpenAI-compatible-ish envelope
GET  /v1/models                # normalized model catalog
POST /v1/chat                  # non-streaming convenience wrapper
DELETE /v1/conversations/{id}
```

**Knowledge**
```
GET  /v1/knowledge/bases
POST /v1/knowledge/search      # { query, kb_id?, top_n, with_scores }
POST /v1/knowledge/ingest      # { uri | text | upload }  → async job
```

**Devices**
```
GET  /v1/devices?group=...
GET  /v1/devices/{id}/status
POST /v1/devices/{id}/diagnostics        # { checks: [ping, traceroute, dns, dhcp, iface] }
POST /v1/devices/{id}/config/dry-run     # { uci_template | diff } → validation plan
POST /v1/devices/{id}/config/apply       # requires approval; returns device_task
GET  /v1/devices/{id}/tasks/{taskId}     # task status
POST /v1/devices/{id}/rollback           # last snapshot
```

**Policy, audit, meta**
```
GET  /v1/policies
POST /v1/audit/query
GET  /v1/health
GET  /v1/ready
```

**Auth**
```
POST /v1/auth/login             # or OIDC redirect
POST /v1/auth/api-keys
```

### 11.2 Internal gRPC (mTLS mesh)

| proto | key RPCs |
|---|---|
| `engine` | `Stream(StreamReq) stream (StreamEvent)`, `Chat`, `GetConversation` |
| `provider` | `Chat`, `ChatStream`, `Embed`, `Vision`, `Rerank`, `ListModels`, `Health` |
| `knowledge` | `Search`, `Ingest`, `DeleteKb` |
| `device` | `GetStatus`, `RunDiagnostics`, `ExecutePlan`, `Rollback`, `ListSnapshots` |
| `policy` | `CheckOutput`, `CheckInput`, `AuthorizeDeviceOp`, `EmitAudit` |
| `telemetry` | `IngestBatch`, `StreamEvents` |

### 11.3 MCP (Model Context Protocol)
The gateway exposes an **MCP server** so external AI assistants can query and
manage devices through the same authorization layer — making the copilot itself
a tool rather than only an end-user product.

### 11.4 Envelope conventions
- All public endpoints return `{ ok, data?, error?, request_id }`.
- Streaming uses SSE events: `event: delta | tool_call | tool_result | done | error`.
- Idempotency keys accepted on `config/apply` and `ingest`.

---

## 12. Sequence Diagrams

### 12.1 Chat with RAG + tool calling (happy path)

```
User          Gateway        Engine        Policy       Knowledge      ProviderGw        DeviceCtrl
 │  POST chat   │             │              │             │              │                │
 │─────────────>│  Stream()    │              │             │              │                │
 │              │────────────>│              │             │              │                │
 │              │             │── Query rewrite (optional, via ProviderGw)                 │
 │              │             │             │             │              │                │
 │              │             │─────────────│─ CheckInput (prompt injection scan)
 │              │             │             │─ok          │              │                │
 │              │             │── Search(query)──────────────────────────>│                │
 │              │             │─────────────────────────────>│             │                │
 │              │             │<── candidates (top 50) ─────│             │                │
 │              │             │── Rerank(query, candidates)───────────────>│                │
 │              │             │<── top 8 ──────────────────│              │                │
 │              │             │                             │              │                │
 │              │             │── Chat(system+ctx, tools)────────────────>│                │
 │              │             │<── tool_call: run_diagnostics ────────────│                │
 │  event: tool_call   │       │                             │              │                │
 │              │             │── ExecutePlan(diagnostics)──────────────────────────────>│
 │              │             │<── results ─────────────────────────────────────────────│
 │              │             │── Chat(results) ────────────────────────>│                │
 │              │             │<── answer ───────────────────────────────│                │
 │  event: done  │             │── EmitAudit(tool_calls, tokens) ────────│                │
 │              │             │             │                             │                │
 │              │             │             │─ audit logged              │                │
 │              │             │             │                             │                │
```

### 12.2 Provider failover

```
Knowledge       ProviderGw            Adapter A        Adapter B
   │  Embed()     │                      │                 │
   │─────────────>│── try A (bge-m3) ──>│                 │
   │              │<── 5xx/timeout ─────│                 │
   │              │── circuit open ──>│                 │
   │              │── try B (NV-Embed)──────────────────>│
   │              │<── embeddings ───────────────────────│
   │<── embeddings│                      │                 │
   │              │── EmitUsage(A fail, B ok)             │
```

### 12.3 Device config change with approval

```
User         Gateway       Engine      Policy       DeviceCtrl      RouterAgent
 │ dry-run     │             │             │             │               │
 │────────────>│────────────>│             │             │               │
 │             │             │── build diff/template ────>│               │
 │             │             │             │             │── render + UCI validate ──>│
 │             │             │             │             │<── ok (dry-run) ───────────│
 │             │             │<── plan ─────────────────│               │
 │<── plan ────│             │             │             │               │
 │ approve apply │            │             │             │               │
 │────────────>│────────────>│── AuthorizeDeviceOp(scope=devices.write)   │
 │             │             │             │─ ok + guardrail rules       │
 │             │             │── ExecutePlan(apply, approved_by=user) ───>│
 │             │             │             │             │── snapshot_before ───>│
 │             │             │             │             │── apply ─────────────>│
 │             │             │             │             │<── ok ────────────────│
 │             │             │             │             │── verify + snapshot_after
 │             │             │<── task result ──────────│               │
 │<── result ──│             │             │             │               │
 │             │             │── EmitAudit(apply, diff, actor)            │
```

### 12.4 Knowledge ingestion pipeline

```
Admin      Knowledge       ProviderGw       Qdrant          Postgres
 │ ingest    │                 │              │                │
 │──────────>│── load + chunk  │              │                │
 │           │── Embed(chunks)─────────────>│                │
 │           │<── vectors ──────────────────│                │
 │           │── upsert(points) ────────────────>│           │
 │           │<── ok ────────────────────────────│           │
 │           │── insert documents/chunks ──────────────────>│
 │<── job ok │                 │              │                │
```

---

## 13. Security Model

### 13.1 Principles
- **Zero trust / least privilege.** Each service has its own identity (mTLS
  certs), scoped service account, and no direct DB access from untrusted layers.
- **Defense in depth** on the edge: routers are treated as hostile/broken.

### 13.2 Transport & mesh
- Public traffic: TLS 1.3, HSTS. Internal traffic: **mTLS** mesh (SPIFFE-style
  identities per service).
- API Gateway is the only internet-exposed surface.

### 13.3 Secrets & credentials
- Provider API keys stored encrypted (AES-256-GCM, envelope encryption via KMS)
  in `provider_creds`, retrieved on-demand by Provider Gateway. Never in
  service config, never logged.
- Docker secrets / Kubernetes Secrets + KMS; rotation schedules enforced.

### 13.4 Identity & authorization
- OIDC + local accounts; RBAC with **scopes** (`ai.chat`, `devices.read`,
  `devices.write`, `admin`, `audit.read`).
- Device operations are doubly gated: RBAC scope **and** Policy guardrail rules.
- Per-device access (user A cannot touch devices they don't own) — enforced by
  tenant + device membership checks in Device Controller.

### 13.5 Mutating operations safety (non-negotiable)
1. Dry-run always produces a plan (diff + validation) before any apply.
2. Apply snapshots config before and after; on post-apply health regression or
   explicit request, **automatic rollback**.
3. Mutating device tasks require explicit human approval unless a tenant policy
   allows narrow auto-apply (still dry-run + validate).
4. Agent-side allowlist: the router agent only executes commands from an
   explicit allowlist; unknown commands are refused even if signed.

### 13.6 AI/LLM security
- **Prompt injection defense**: Policy service filters inputs and outputs;
  instruction-hierarchy prompts; tool results are treated as untrusted data,
  never as instructions.
- **Capability gating**: model can only call tools the user is authorized to
  invoke; tools never expose raw secrets or shell access.
- **SSRF protection**: Provider Gateway and Device Controller fetch only
  allowlisted destinations; no arbitrary user-supplied URLs in the model plane.
- **Redaction**: PII/keys/passwords redacted in outputs and audit trails.

### 13.7 Audit & tamper-evidence
- Every AI call, tool call, config change, approval, and rollback emits an audit
  event signed with a per-tenant HMAC key; queryable via `POST /v1/audit/query`.

### 13.8 Abuse controls
- Rate limiting per user/IP/API key; per-tenant token budgets; cost ceilings to
  cap cloud spend; anomaly alerting on usage spikes.

---

## 14. Deployment Model

### 14.1 Profiles (configurable, same artifacts)

| Profile | Where | Providers | Use case |
|---|---|---|---|
| **offline** | Home-lab / air-gapped | Ollama, LM Studio, local ONNX embed/rerank | Privacy, no internet |
| **hybrid** | Home server + cloud | Ollama/vLLM local + OpenAI/OpenRouter fallback | Best-effort quality with local-first |
| **managed** | Kubernetes | any | Fleets, HA, multi-tenant |
| **edge** | Router(s) + home server | router agent on device; heavy AI on LAN server | Single-home setup |

### 14.2 Edge placement
- Router Agent runs on-device; control plane + models run on a small home server
  (e.g., a mini-PC or NAS) reachable over LAN or a site-to-site tunnel.
- The Agent opens an outbound WebSocket to Device Controller — no router inbound
  ports, no public IP required.

### 14.3 Multi-tenant managed
- Control plane in Kubernetes; one tenant → isolated namespaces, per-tenant
  Qdrant collections and Postgres schemas; quotas enforced at Gateway.

### 14.4 Model serving options
- **Ollama**: containerized, CPU/GPU. **vLLM**: GPU node(s), OpenAI-compat.
- **NIM**: NGC containers. **LM Studio**: desktop server on the LAN.
- **OpenAI / OpenRouter**: cloud only, opt-in.
- Model plane may be fully remote (cloud) or fully local (offline profile).

### 14.5 Observability
- OpenTelemetry traces + metrics; Prometheus; Grafana dashboards per service;
  structured logs to Loki. Cost dashboards per provider/tenant/model.

---

## 15. Docker Architecture

### 15.1 Networks
```
 frontend  (gateway)  ← exposed
 internal  (mTLS mesh between services; also Postgres/Qdrant/NATS/Redis)
 models    (isolated: provider-gateway → model servers only)
```

### 15.2 Services (docker-compose)

| Service | Image (multi-stage Go, distroless, non-root) | Exposes |
|---|---|---|
| gateway | `openwrt-ai/gateway` | 443/8080 (frontend) |
| engine | `openwrt-ai/engine` | internal |
| provider-gateway | `openwrt-ai/provider-gateway` | internal + models net |
| knowledge | `openwrt-ai/knowledge` | internal |
| device-controller | `openwrt-ai/device-controller` | internal |
| telemetry | `openwrt-ai/telemetry` | internal |
| policy | `openwrt-ai/policy` | internal |
| auth | `openwrt-ai/auth` | internal |
| postgres | `postgres:17` | internal (volume) |
| qdrant | `qdrant/qdrant` | internal (volume) |
| nats | `nats:alpine` + jetstream | internal (volume) |
| redis | `redis:7-alpine` | internal |
| otel-collector / prometheus / grafana / loki | observability stack | internal |

### 15.3 Model server profiles (optional, opt-in)
```yaml
services:
  ollama:
    image: ollama/ollama
    networks: [models]
    volumes: [ollama-models]
    deploy: { resources: { reservations: { devices: [gpu] } } }
  vllm:
    image: vllm/vllm-openai
    command: ["--model", "Qwen/Qwen2.5-Coder-7B-Instruct"]
    networks: [models]
```

### 15.4 Image/build rules
- Multi-stage builds: `golang:1.24-alpine` build → `gcr.io/distroless/static`
  runtime; one binary per service; non-root UID; `CAP_DROP` all.
- Health checks (`/v1/health`) wired into compose restart policies.
- Reproducible builds via `go.work` + `go.sum`; SBOM attached to release
  artifacts.

### 15.5 Router Agent artifact
- Cross-compiled static binaries: `linux/mipsle`, `linux/mips`, `linux/arm64`,
  `linux/arm/v7`. Packaged as an **opkg** `.ipk` in `deploy/openwrt/`.
- Agent connects out to Device Controller; local allowlist in
  `/etc/openwrt-ai/agent.toml`.

---

## 16. Decision Log

| # | Decision | Alternative considered | Rationale |
|---|---|---|---|
| D1 | **Go** for control plane + agent | Rust, Python | Single language; static musl binaries for router targets; great concurrency for streaming |
| D2 | **Provider Gateway** as dedicated service | SDK-in-each-service | Centralizes routing, failover, cost accounting; keeps "no provider SDK" hard rule |
| D3 | **NATS JetStream** internal bus | MQTT, Kafka | Streaming + durable queues, small footprint, easy on-prem |
| D4 | **Qdrant** vector store | Milvus, LanceDB, pgvector | Dense+sparse hybrid in one system, self-hostable, low ops |
| D5 | **Postgres** as system of record | none | Standard, robust, JSONB for flexible payloads |
| D6 | **OpenAI-compatible core** for most adapters | Native adapters everywhere | All 6 providers expose it; reduces adapter surface; native wrappers only where they add value (Ollama, NIM rerank) |
| D7 | **Content-block multimodal** for vision | Parallel vision API | Reuses chat/streaming/routing; vision = capability flag, not new protocol |
| D8 | **Local cross-encoder rerank default** | Require NIM/remote reranker | Works fully offline; NIM optional upgrade |
| D9 | **Router agent with outbound tunnel** | Inbound SSH to routers | No inbound ports; works behind CGNAT; allowlist enforced device-side |

---

## 17. Open Questions for Approval

1. **Language**: Confirm **Go** (recommended) vs Rust/Python.
2. **Vector DB**: Confirm **Qdrant** vs pgvector (simpler, one fewer service) vs Milvus.
3. **Internal bus**: Confirm **NATS JetStream** vs MQTT (already familiar to the
   OpenWrt ecosystem).
4. **Scope of v1**: Full microservice mesh vs a **modular monolith** first
   (single binary, modules behind interfaces) to reduce ops burden for a
   home-lab product, then split later.
5. **Multi-tenancy**: Is this a **single-tenant** product (your own routers) or
   **multi-tenant SaaS-ready**? This drives the Auth model and collection
   isolation.
6. **UI scope**: Is the Web UI (Vue) in-scope for v1, or API/MCP + LuCI plugin
   only?
7. **Autonomy level**: Confirm the approval gate for config changes (recommend:
   human approval mandatory, with opt-in narrow auto-apply).
8. **Models**: Any specific preferred models for embed/rerank/chat/vision, or
   adopt the catalog defaults proposed?

---

*End of architecture draft. Awaiting approval before any implementation or
prototyping work.*
