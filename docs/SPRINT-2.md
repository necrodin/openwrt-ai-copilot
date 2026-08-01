# Sprint 2 — AI Provider Abstraction Layer

Status: **complete** (verification: 78 pytest passed, ruff clean, backend boots
with a provider config file).

## Goal

Make the application provider-independent: chat, streaming, embeddings, vision,
and reranking behind four stable interfaces, six concrete adapters, and
config-driven switching — with **no provider SDK dependency anywhere**.

## Key decisions

- **Interfaces** (`ai/src/ai/core/protocols.py`): abstract base classes
  `ChatProvider`, `EmbeddingProvider`, `VisionProvider`, `RerankerProvider` on
  top of `Provider`. Every provider exposes `health()`, `capabilities()`,
  `token_usage()`, and `static_capabilities()`; `supports()` checks a
  capability. Capability identifiers are string constants
  (`CAPABILITY_CHAT`, `CAPABILITY_STREAM`, `CAPABILITY_EMBEDDINGS`,
  `CAPABILITY_VISION`, `CAPABILITY_RERANK`, `CAPABILITY_TOOLS`).
- **Empty model string = provider default**: a request with `model=""` resolves
  to the provider's configured model. This is what makes providers swappable
  via config without touching callers.
- **No SDKs, ever**: all adapters call plain HTTP through
  `ProviderTransport` (httpx). Two streaming wire formats: OpenAI SSE and
  Ollama NDJSON. A client (e.g. `httpx.MockTransport`) can be injected for
  tests; injected clients still receive base URL, auth, and extra headers.
- **Capability detection** (`providers/capabilities.py`): combines the
  provider's static defaults, configured models, and a runtime model catalog
  probe (model-name markers). An explicit `capabilities` override in the
  config wins and is reported as fully static. Runtime probes mark the result
  `static=False`. This is the "future capability detection": a provider that
  starts serving vision/embedding models is picked up automatically.
- **Vision** is a multimodal chat: `VisionProvider.vision()` delegates to
  `chat()` with `ContentPart` image blocks. `BaseProvider` implements this, so
  adapters get it for free once their `chat()` handles parts.
- **Token accounting**: every call merges a `Usage` into a `TokenUsage` (per
  capability buckets, calls, errors, cost via `cost_per_1k_*` config).
  `token_usage()` returns a deep-copied snapshot.
- **Config** (`providers/config.py`): `providers.yaml`/`.toml` with a
  `default_provider`, per-provider entries, and secret-free config (API keys
  referenced by env var name). `type` defaults to the map key; an explicit type
  must match the key. `extra="forbid"` catches typos.
- **Factory** (`providers/factory.py`): `create_provider_manager(config)`
  builds a `ProviderManager`. `get_for_capability(capability, preferred=...)`
  routes synchronously using declared capabilities (preferred → default → any).
  Built-in types are registered at import; `register_provider`/`unregister_provider`
  support custom types. Capabilities are also mirrored into `ai.core.registry`.

## Adapters (`providers/src/providers/`)

| Provider | Type | Notes |
|---|---|---|
| Ollama | `ollama` | Native API (`/api/tags`, `/api/chat` NDJSON, `/api/embed`). |
| NVIDIA NIM | `nim` | OpenAI-compatible + `/v1/rerank`; `rerank()` implemented. |
| OpenAI | `openai` | OpenAI-compatible; chat/stream/embeddings/tools. |
| OpenRouter | `openrouter` | OpenAI-compatible. |
| LM Studio | `lmstudio` | OpenAI-compatible, local. |
| vLLM | `vllm` | OpenAI-compatible, local. |

All OpenAI-compatible adapters reuse `OpenAICompatibleProvider`
(`providers/compat_provider.py`); they only set `provider_type` and
`capability_defaults`. Unsupported capabilities raise
`UnsupportedCapabilityError`; `capabilities()` reports them as absent so
callers detect support instead of guessing.

## Backend integration

- `backend/app/main.py` lifespan builds the `ProviderManager` from
  `PROVIDER_CONFIG_FILE` (default `providers.yaml`; missing file = empty
  manager, app still boots) and closes transports on shutdown.
- `backend/app/api/v1/providers.py` (mounted at `/api/v1`): read-only admin
  endpoints — list providers, detail, health, capabilities, usage, models.
  No mutating endpoints; switching providers is a config edit.

## Dependencies

- `providers/pyproject.toml` now depends on `httpx` and `pyyaml`.
- `backend/pyproject.toml` depends on `openwrt-ai-providers`; dev extras
  already include `pytest-asyncio`.

## Tests (tests/unit/)

`test_providers_config.py`, `test_providers_capabilities.py`,
`test_providers_transport.py`, `test_providers_openai_compat.py`,
`test_providers_ollama.py`, `test_providers_nim.py`,
`test_providers_factory.py`, `test_token_usage.py`,
`test_api_providers.py` (backend endpoints via dependency overrides). All use
`httpx.MockTransport` — no network. `tests/unit/providers_helpers.py` provides
`make_provider` / `make_mock_client`.

## Run

```bash
make test        # pytest (78 tests)
make lint        # ruff check + format check
```

Switching providers = editing `providers.yaml` only (see `providers.example.yaml`).
