# Sprint 9A — Retrieval Core

## Goal

Deliver the **Retrieval Core** — the first half of RAG, fully provider-independent,
with **no LLM connection, no streaming, and no AI Chat changes**. The pipeline ends
at a ready-for-LLM `PromptRequest`/`PromptResponse` that a later sprint hands to the
AI layer.

```
Question → Embedding → VectorStore → Merge Results → Remove Duplicates
         → Context Builder → Prompt Builder → Ready For LLM
```

## Scope

Implemented entirely inside the `rag` package (version `0.5.0-alpha`, dist
`openwrt-ai-rag 0.5.0a1`):

- **Retriever** — `VectorRetriever` (embed → search → merge → dedupe → rank)
- **Context Builder** — `DefaultContextBuilder` (group → cap → cite → history)
- **Prompt Builder** — `DefaultPromptBuilder` (system + history + context + question)
- **Citations** — `DefaultCitationBuilder` (numbered `[N]` refs + snippets)
- **Conversation Memory** — `InMemoryMemoryStore`, `RollingConversationMemory`,
  `ConversationManager` (rolling window, trimming, compression, snapshots)
- **Memory** — `MemoryStore`, `ConversationState`, `MemorySnapshot`
- **Token Management** — `HeuristicTokenEstimator`, `TokenBudgetManager`
  (max context/prompt/documents, automatic reduction via `DefaultPromptOptimizer`)
- **Caching** — `InMemoryContextCache` (retrieval + prompt, TTL, SHA-256 checksum keys)
- **Models** — `RetrievedDocument`, `RetrievedChunk`, `Citation`, `PromptContext`,
  `PromptRequest`, `PromptResponse`, `ConversationState`, `MemorySnapshot`, `Message`
- **Orchestration** — `RetrievalEngine` (cache → retrieve → context → prompt → budget → remember)

The Sprint-1 stub (`pipeline.py`, the `chunking/`/`retrieval/`/`reranking/` placeholder
packages) is left untouched.

## Design decisions

### Provider independence by construction
`rag` imports only the **`vectorstore` interface** plus its own modules. It never
imports `ai`, `providers`, `knowledge`, or any SDK. Embedding and language detection
are **injected callables**:

```python
Embedder = Callable[[str], Awaitable[list[float]]]  # providers' EmbeddingFactory satisfies this
LanguageDetector = Callable[[str], str] | None  # knowledge's detect_language can be wired in
```

Token estimation mirrors the `providers` convention (`ceil(len(text) / 4)`) so
retrieval-side and provider-side accounting agree until a real tokenizer lands.

### Every stage is a protocol
`Retriever`, `ContextBuilder`, `PromptBuilder`, `PromptOptimizer`, `TokenEstimator`,
`MemoryStore`, `ConversationMemory`, and `ContextCache` are ABCs/Protocols in
`protocols.py`; concrete defaults live in sibling modules and are swappable by
configuration or dependency injection.

### Retrieval: merge + dedupe, not just search
`VectorRetriever.retrieve` embeds the query, searches every configured collection
concurrently (`asyncio.gather`), min-max normalises cosine scores per collection,
weights them by `CollectionRef.weight`, merges, and de-duplicates — first by chunk id,
then (optionally) by canonical text checksum — keeping the highest score per duplicate.

Chunk metadata follows a documented convention a future knowledge→vectorstore bridge
should write: `document_id`, `index`, `heading`, `title`, `source`, `reference`,
`format`, `language`, `checksum`, `version`. When metadata is absent the chunk id
(`<document_id>#<index>`) is parsed as a fallback.

### Conversation memory without an LLM
The rolling window keeps the newest `window_size` messages; `history(max_tokens=…)`
fits the most recent turns under a token budget; and once `pending_turns` reaches the
compression threshold the oldest turns are folded into a deterministic, **extractive**
`MemorySnapshot` (first sentences + keyword extraction) — same input, same snapshot.

### Automatic context reduction
`DefaultPromptOptimizer` drops the lowest-ranked chunks first, then the oldest history,
then the entire context block; if the minimal prompt still cannot fit it raises
`ContextLimitError`.

### Caching with checksum keys
`InMemoryContextCache` stores retrieval results (TTL 300 s) and built prompts (TTL 60 s)
keyed by `SHA-256` checksums over (query, collection signature, top_k, namespace,
history signature). Stateless repeated questions short-circuit the whole pipeline
(`cached=True`).

## What was added

```
rag/pyproject.toml          deps → openwrt-ai-vectorstore, pydantic (+ optional yaml)
rag/src/rag/__init__.py     version 0.5.0-alpha + public exports
rag/src/rag/models.py       all Sprint 9A models
rag/src/rag/errors.py       RetrievalError hierarchy
rag/src/rag/protocols.py    stage interfaces
rag/src/rag/config.py       RetrievalConfig + sub-configs, YAML loading
rag/src/rag/tokens.py       HeuristicTokenEstimator, TokenBudgetManager
rag/src/rag/retriever.py    VectorRetriever
rag/src/rag/citations.py    DefaultCitationBuilder
rag/src/rag/context.py      DefaultContextBuilder
rag/src/rag/prompt.py       DefaultPromptBuilder, DefaultPromptOptimizer
rag/src/rag/memory.py       InMemoryMemoryStore, RollingConversationMemory,
                            ConversationManager, summarize_messages
rag/src/rag/cache.py        InMemoryContextCache
rag/src/rag/engine.py       RetrievalEngine
```

## Tests

98 new tests across `tests/unit/test_rag_*.py` (models, tokens, retriever, context,
citations, prompt, cache, memory, engine) using fakes — never a real network, vector
store, or LLM. **Full suite: 500 passed**, `make lint` clean.

## Run

```python
import asyncio
from rag import RetrievalEngine, VectorRetriever, InMemoryContextCache
from rag.memory import RollingConversationMemory
from providers.embedding import EmbeddingFactory  # later sprint wires this


async def main():
    retriever = VectorRetriever(vector_store, embedder=embed_query)  # inject real embedder
    engine = RetrievalEngine(
        retriever,
        cache=InMemoryContextCache(),
        memory=RollingConversationMemory(),
    )
    response = await engine.answer("How do firewall zones work?", conversation_id="c1")
    # response.prompt.messages -> ready for the AI layer
    await engine.aclose()
```

## Roadmap note

Sprint 9B is expected to connect the AI layer: map `PromptRequest` to a chat model,
call the provider, stream chunks back, record the assistant turn via
`engine.complete_turn(...)`, and surface citations in the UI. Sprint 9A ships the
entire retrieval side so that work is purely connective.
