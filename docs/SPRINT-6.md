# Sprint 6 — Embedding Platform

Status: **complete** (verification: 166 pytest passed, ruff clean; no network —
all provider calls go through mocked transports).

## Goal

A provider-independent embedding platform: turn text into vectors through
**any** configured provider — NV-Embed (NVIDIA NIM), OpenAI, Ollama, OpenRouter,
LM Studio, vLLM — behind one async `EmbeddingFactory`. No vendor SDK and no
direct OpenAI/NVIDIA calls anywhere; every request goes through the
`ProviderManager` / `EmbeddingProvider` interface built in Sprint 2. No vector
DB, no RAG, no search — just the embedding capability.

## What was added

### `EmbeddingFactory` (`providers/src/providers/embedding.py`)

The public surface of the platform:

| Method | Behaviour |
|---|---|
| `embed(text, preferred=…)` | Single text → vector. |
| `embed_batch(texts, batch_size=…)` | Batched embedding; returns one vector per input. |
| `embed_response(texts, …)` | Same batching, returns an `EmbeddingResponse` with aggregated `Usage`. |
| `health(preferred=…)` | `{provider_name: bool}` over the embedding-capable providers. |
| `token_usage()` | Aggregated `TokenUsage` (total + per-capability), from `_manager`. |
| `embedding_providers()` | Static (no network) list of embedding-capable providers. |

- **Provider selection**: `ProviderManager.get_for_capability(CAPABILITY_EMBEDDINGS,
  preferred=…)` first; if the static pass finds nothing, a runtime capability
  probe (`await provider.supports(CAPABILITY_EMBEDDINGS)`) detects providers
  that only expose embeddings once configured (e.g. Ollama with `embed_model`).
- **Batching**: default 64, overridden by the provider's `embed_batch_size`,
  then by the caller's `batch_size`. `chunk_texts()` splits inputs and the
  results are flattened back to one vector per input.
- **Retries**: `RetryPolicy(max_retries=3, exponential backoff + jitter)` by
  default — embeddings are idempotent. Retryable: `ProviderUnavailableError`,
  `RateLimitError`, `asyncio.TimeoutError`. `RetryPolicy(max_retries=0)` for
  fail-fast callers.
- **Timeout**: per-call `asyncio.wait_for` (`timeout_seconds`), surfaced as
  `EmbeddingError`.
- **Errors**: `EmbeddingError` (base, wraps the last failure) and
  `NoEmbeddingProviderError` when no configured provider can embed.

### Providers

- **`NVEmbedProvider`** (`providers/src/providers/nv_embed.py`): first-class
  NVIDIA adapter (embeddings-only, `provider_type = "nvembed"`). Resolves
  `nvidia/NV-Embed-QA-Mistral-4B` by default, sends the retrieval-aware
  `input_type` (`query` | `passage`) field, and normalizes vectors when
  requested. Registered as a built-in provider type.
- **NIM / OpenRouter / LM Studio**: `embeddings` added to their declared
  capability defaults (they reuse the shared OpenAI-compatible implementation).
- **Shared protocol** (`providers/src/providers/openai_compat.py`):
  `request_embeddings()` gained `include_input_type` (only NV-Embed sends
  `input_type`) and `normalize`; `normalize_vector()` L2-normalizes; `_parse_usage`
  falls back to `total_tokens` when `prompt_tokens` is absent (NIM-style usage).

### Model layer (`ai/src/ai/core/models.py`)

- `EmbeddingInputType = Literal["query", "passage"]`.
- `EmbeddingRequest` gained `input_type` and `normalize` (both optional).
- `TokenUsage.absorb()` — fold one usage snapshot into another (used to
  aggregate across providers).

### Config & docs

- `providers.yaml` schema: new `nvembed:` block (NVIDIA API key,
  `embed_model`, `embed_dimensions`, `embed_batch_size`); `embed_batch_size`
  for ollama; `embed_model` for openrouter/lmstudio. Mirrored in
  `providers.example.yaml`.
- Package exports in `providers/__init__.py`: `EmbeddingFactory`,
  `NVEmbedProvider`, `DEFAULT_NV_EMBED_MODEL`, `RetryPolicy`, `chunk_texts`,
  `EmbeddingError`, `NoEmbeddingProviderError`, `RETRYABLE_EXCEPTIONS`.

## Tests

New/updated suites (all mocked transports, no network):

- `tests/unit/test_providers_nv_embed.py` — capability defaults
  (`{"embeddings"}` only), built-in registration, model resolution order
  (request → config → default), `input_type` on the wire, normalization,
  `dimensions()`, health, `total_tokens` → `prompt_tokens` usage fallback,
  error surfacing.
- `tests/unit/test_embedding_factory.py` — `chunk_texts`; single / batched /
  chunked embedding with aggregated usage; provider `embed_batch_size`
  respected; empty batch makes no provider call; `preferred` provider used;
  runtime detection picks up an Ollama provider configured with `embed_model`;
  retry-after-transient-failure (2×503 then success); give-up after
  `max_retries`; timeout → `EmbeddingError`; `health()` per provider;
  `embedding_providers()` lists static capability only; `token_usage()`
  aggregates across providers.
- `tests/unit/test_providers_nim.py` — `embeddings` via `/v1/embeddings` with
  `total_tokens`-only usage.
- `tests/unit/test_token_usage.py` — `TokenUsage.absorb()` totals/errors and
  non-mutation of the source.

`make test` runs 166 tests; `make lint` is clean.

## Run

```bash
# configure an embedding-capable provider (see providers.example.yaml)
cp providers.example.yaml providers.yaml   # e.g. nvembed or ollama + embed_model
```

The factory is not yet wired to an HTTP endpoint (that is a later sprint); to
exercise it directly:

```python
from providers.embedding import EmbeddingFactory
from providers.factory import create_provider_manager

manager = create_provider_manager("providers.yaml")
factory = EmbeddingFactory(manager)
vector = await factory.embed("what is NAT")
vectors = await factory.embed_batch(["a", "b", "c"], batch_size=2)
```

## Roadmap note

This sprint delivers the embedding capability on top of the Sprint-2 provider
abstraction. Vector storage, retrieval, and RAG wiring remain later sprints;
chat stays grounded exclusively in the live router snapshot (Sprint 5).
