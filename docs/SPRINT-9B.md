# Sprint 9B — Retrieval Engine → AI Chat Integration

## Goal

Connect the Sprint 9A **Retrieval Core** to **AI Chat** so every question is
answered from the knowledge base: retrieved context is auto-injected into the
prompt, answers are streamed, and every claim carries a citation with full
provenance (knowledge source, document name, section, chunk id, similarity score,
rerank score).

```
AI Chat
   ↓
EmbeddingFactory → EmbeddingCache → VectorRetriever → VectorStore
   ↓
Reranker (ProviderReranker / DummyReranker)
   ↓
Context Builder → Prompt Builder
   ↓
Chat Provider → Streaming Response (SSE)
```

## Scope

Implemented across three layers, keeping every existing module intact:

- **`providers`** — `RerankFactory`, a provider-independent rerank facade
  (mirrors `EmbeddingFactory`) over the existing `RerankerProvider` ABC and the
  existing NVIDIA NIM `rerank()` adapter. No SDK, no duplicate logic.
- **`rag` core** — a `Reranker` protocol plus a deterministic `DummyReranker`,
  and a backward-compatible `reranker` hook on `RetrievalEngine` (applied after
  retrieval, before context building). Core stays provider-independent.
- **`rag.ai`** (new subpackage) — the *only* place `rag` touches `ai`/`providers`:
  `RAGEngine`, `RAGSession`, `RAGConfiguration`, `RAGResponse`, `RAGCitation`,
  `RAGStreamEvent`, `RAGUsage`, `EmbeddingCache`, `CachedEmbedder`, and the
  `ProviderReranker` bridge.
- **`backend`** — an opt-in `RAGService` loaded from `rag.yaml`; `/chat` and
  `/chat/stream` route through the `RAGEngine` when RAG is enabled and fall back
  to the existing router-state chat otherwise. The existing API is unchanged.

Sprint 9A modules (`rag/models.py`, `rag/retriever.py`, `rag/context.py`, …) and
the Sprint-1 stubs (`rag/pipeline.py`, `chunking/`/`retrieval/`/`reranking/`) are
**not rewritten**; only `rag/protocols.py`, `rag/engine.py`, `rag/reranker.py`
(new), and `rag/__init__.py` gained a small addition.

## RAG flow

1. **Question** — the user message arrives at the chat endpoint.
2. **Embed** — `EmbeddingFactory.embed()` (query type) through the
   `CachedEmbedder`, which short-circuits repeat queries via `EmbeddingCache`
   (SHA-256 keyed, bounded, thread-safe).
3. **Retrieve** — `VectorRetriever` searches the configured collections
   concurrently, min-max normalises scores, merges, de-duplicates, and applies
   the similarity threshold.
4. **Rerank (optional)** — `ProviderReranker` re-scores chunks through
   `RerankFactory` (e.g. NVIDIA NIM); the vector-store similarity is preserved
   alongside the rerank score so citations can show both. Without a configured
   reranker the deterministic `DummyReranker` keeps the vector-store order.
5. **Context + Prompt** — `DefaultContextBuilder` groups, caps, and cites the
   chunks; `DefaultPromptBuilder` renders system + history + context + question.
   History comes from the per-conversation rolling memory.
6. **Generate** — the prompt is sent to the chat provider (config-selectable),
   streaming token deltas back over SSE.
7. **Record** — the assistant turn is stored in conversation memory (and the
   durable SQLite chat store), so follow-up questions build on previous turns.

## Chat integration

- **Auto-injected context** — the rendered user message always contains the
  retrieved `Context:` block plus the `Question:`.
- **Streaming** — the stream emits an ordered timeline:
  `session` → `retrieval` (citations ready) → `generation_started` →
  `delta` (tokens) → `citations` → `done`, or `error` at any point.
- **Markdown** — the grounded system prompt instructs Markdown output; the
  existing chat UI renders it.
- **Memory / multi-turn** — `RAGSession` owns a conversation id; the rolling
  conversation memory carries history across turns, and the backend replays
  durable SQLite history into a fresh session's memory after a restart.
- **Context expansion** — `RAGSession.expand_context(query)` retrieves a broader
  set and returns *new* citations (chunks the conversation has not cited yet),
  so "give me more detail" surfaces fresh sources.

## Citations

Every citation exposes:

| Field | Meaning |
|---|---|
| `source` | Knowledge source (e.g. `knowledge/docs/wireguard.md`) |
| `document` | Document name (e.g. `wireguard.md`) |
| `section` | Heading within the document |
| `chunk_id` | `document_id#index` chunk identifier |
| `similarity_score` | Vector-store similarity (0..1) |
| `rerank_score` | Rerank score (0..1), or `null` when no reranker ran |
| `confidence` | Rerank score if present, else similarity |
| `snippet` | Short excerpt so the citation stands alone |

## Configuration (`rag.yaml`)

| Key | Default | Meaning |
|---|---|---|
| `collection` | `documents` | Vector collection to search |
| `namespace` | `default` | Namespace within the collection |
| `vector_dimensions` | `768` | Dimensions the collection is created with |
| `top_k` | `8` | Candidate chunks per query |
| `max_documents` | `6` | Max source documents in the context |
| `score_threshold` | `0.0` | Minimum similarity (0..1); `null` disables |
| `provider` / `model` | — | Chat provider preference / model override |
| `temperature` | — | Sampling temperature (0..2) |
| `embed_provider` / `embed_model` | — | Query embedding provider/model |
| `rerank_provider` / `rerank_model` | — | Reranker selection (e.g. `nim`); empty = dummy |
| `memory_enabled` / `memory_window` | `true` / `20` | Conversation memory |
| `use_cache` | `true` | Retrieval/prompt/embedding caching |
| `context_expansion` | `true` | Allow on-demand context expansion |
| `system_prompt` | grounded default | Override the system prompt |

Copy `rag.example.yaml` → `rag.yaml` to enable RAG chat. Missing/unparseable
`rag.yaml` disables RAG and the existing router-state chat path is used verbatim
(no API change). Rerank provider selection is configurable; a configured reranker
that is unavailable degrades to the dummy fallback at call time.

## Backend

- `RAGService` owns the shared persistent stack: SQLite `VectorStore` (path from
  `RAG_VECTOR_STORE_PATH`), the `CachedEmbedder`, the reranker, and the shared
  retrieval cache. Per-conversation `RetrievalEngine`s are memoized so memory
  survives across requests.
- `load_rag_service()` runs in the lifespan; any failure disables RAG gracefully.
- `/chat` returns the reply **plus** `citations`, `usage`, and `rag: true`.
- `/chat/stream` forwards the full event timeline; the non-RAG SSE contract is
  unchanged.

## What was created / modified

```
created  providers/src/providers/rerank.py        RerankFactory + errors
created  rag/src/rag/reranker.py                  DummyReranker
created  rag/src/rag/ai/__init__.py               rag.ai public API
created  rag/src/rag/ai/errors.py                 RAGError hierarchy
created  rag/src/rag/ai/models.py                 RAGCitation, RAGResponse,
                                                  RAGStreamEvent, RAGUsage
created  rag/src/rag/ai/config.py                 RAGConfiguration
created  rag/src/rag/ai/cache.py                  EmbeddingCache, CachedEmbedder
created  rag/src/rag/ai/rerank.py                 ProviderReranker, build_reranker
created  rag/src/rag/ai/engine.py                 RAGEngine + builders
created  rag/src/rag/ai/session.py                RAGSession
created  backend/app/services/rag_service.py      RAGService, load_rag_service
created  rag.example.yaml                         Example RAG configuration

modified providers/src/providers/__init__.py      export rerank facade
modified rag/src/rag/protocols.py                 Reranker protocol
modified rag/src/rag/engine.py                    optional reranker hook
modified rag/src/rag/__init__.py                  version + rerank exports
modified rag/pyproject.toml                       0.5.0a2, optional ai extra
modified backend/app/core/config.py               RAG settings
modified backend/app/main.py                      lifespan wiring
modified backend/app/api/v1/chat.py               optional RAG routing
modified backend/pyproject.toml                   openwrt-ai-rag dep
```

## Tests

35 new tests: `test_rerank_factory.py` (selection, top-n, retries, usage),
`test_rag_ai_engine.py` (configuration, grounded answers, citations with both
scores, streaming timeline, memory, context expansion, embedding cache, rerank
bridge + core hook), and `test_chat_api_rag.py` (full-stack integration with
mocked transports + a real SQLite store: grounded chat, rerank scores, stream
events, multi-turn memory, RAG disabled by default). **Full suite: 535 passed**,
`make lint` clean.

## Run

```bash
cp rag.example.yaml rag.yaml          # enable RAG chat
cp providers.example.yaml providers.yaml   # add a chat + embedding provider
make dev-backend
```

```python
from rag.ai import RAGEngine, RAGSession, RAGConfiguration
from rag import VectorRetriever, DummyReranker
from providers.embedding import EmbeddingFactory

config = RAGConfiguration.from_file("rag.yaml")
retriever = VectorRetriever(vector_store, embedder=embed_query)
engine = RAGEngine(retriever, configuration=config, provider=chat_provider)
session = RAGSession(engine)
response = await session.answer("How do firewall zones work?")
for citation in response.citations:
    print(citation.document, citation.section, citation.similarity_score)
```

## Performance notes

- Embedding results and retrieved chunks are cached; identical repeat questions
  short-circuit the vector store and (for stateless calls) the prompt build.
- Rerank is a single batched provider call over the already-retrieved top chunks.
- The stream retrieves **before** generation starts, so tokens flow immediately
  once the context is ready.

## Roadmap note

A future sprint can swap the SQLite vector store for Qdrant/Chroma/FAISS purely
via configuration, persist conversation memory and citations durably, and
surface citations in the chat UI.
