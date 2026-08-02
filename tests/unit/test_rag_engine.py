"""RetrievalEngine tests: full pipeline, caching, memory, budgets."""

from __future__ import annotations

import pytest

from rag.cache import InMemoryContextCache
from rag.config import RetrievalConfig, TokenBudgetConfig
from rag.engine import RetrievalEngine
from rag.errors import ContextLimitError
from rag.memory import RollingConversationMemory
from rag.models import PromptResponse
from rag.retriever import VectorRetriever
from vectorstore.models import SearchResult, VectorMetadata


class FakeVectorStore:
    def __init__(self, results: list[SearchResult] | None = None) -> None:
        self.results = results or [
            SearchResult(
                id="doc1#0",
                score=0.9,
                text="OpenWrt firewall rules live in /etc/config/firewall.",
                metadata=VectorMetadata(
                    values={
                        "document_id": "doc1",
                        "index": 0,
                        "title": "OpenWrt Firewall",
                        "source": "wiki",
                        "reference": "firewall",
                    }
                ),
            )
        ]
        self.search_count = 0
        self.embedded_queries: list[str] = []

    async def search(
        self, name: str, request, *, namespace: str | None = None
    ) -> list[SearchResult]:
        self.search_count += 1
        return self.results

    async def aclose(self) -> None:
        pass


def fake_embedder(queries: list[str]):
    async def embed(text: str) -> list[float]:
        queries.append(text)
        return [0.1, 0.2]

    return embed


def build_engine(
    store: FakeVectorStore, *, config: RetrievalConfig | None = None, **kwargs
) -> RetrievalEngine:
    queries: list[str] = []
    retriever = VectorRetriever(store, fake_embedder(queries))
    kwargs.setdefault("cache", InMemoryContextCache())
    kwargs.setdefault("memory", RollingConversationMemory())
    engine = RetrievalEngine(retriever, config=config, **kwargs)
    engine._queries = queries  # type: ignore[attr-defined]
    return engine


async def test_answer_returns_prompt_response() -> None:
    store = FakeVectorStore()
    engine = build_engine(store)
    response = await engine.answer("How do firewall rules work?")
    assert isinstance(response, PromptResponse)
    assert response.query == "How do firewall rules work?"
    assert response.prompt.messages[-1].role == "user"
    assert response.tokens.prompt_tokens > 0
    assert response.tokens.max_tokens == 1000


async def test_answer_retrieval_is_cached() -> None:
    store = FakeVectorStore()
    engine = build_engine(store)
    await engine.answer("same question", top_k=3)
    first = store.search_count
    await engine.answer("same question", top_k=3)
    assert store.search_count == first


async def test_answer_use_cache_false_searches_again() -> None:
    store = FakeVectorStore()
    engine = build_engine(store)
    await engine.answer("q", use_cache=False)
    first = store.search_count
    await engine.answer("q", use_cache=False)
    assert store.search_count == first + 1


async def test_stateless_prompt_cache_hit() -> None:
    store = FakeVectorStore()
    engine = build_engine(store)
    first = await engine.answer("repeated")
    second = await engine.answer("repeated")
    assert first.cached is False
    assert second.cached is True
    assert second.prompt.checksum == first.prompt.checksum


async def test_conversation_records_user_turn() -> None:
    engine = build_engine(FakeVectorStore())
    await engine.answer("How are zones defined?", conversation_id="c1")
    history = engine.memory.history("c1")
    assert [m.content for m in history] == ["How are zones defined?"]
    assert [m.role for m in history] == ["user"]


async def test_remember_false_skips_memory() -> None:
    engine = build_engine(FakeVectorStore())
    await engine.answer("q", conversation_id="c1", remember=False)
    assert engine.memory.history("c1") == []


async def test_complete_turn_records_assistant() -> None:
    engine = build_engine(FakeVectorStore())
    engine.complete_turn("c1", "The zones are defined in /etc/config/firewall.")
    roles = [m.role for m in engine.memory.history("c1")]
    assert roles == ["assistant"]


async def test_history_included_in_prompt() -> None:
    engine = build_engine(FakeVectorStore())
    engine.memory.add("c1", "user", "Earlier I asked about zones.")
    engine.memory.add("c1", "assistant", "Zones control forwarding.")
    response = await engine.answer("Now about firewall rules?", conversation_id="c1")
    contents = [m.content for m in response.prompt.messages]
    assert any("Earlier I asked about zones." in content for content in contents)


async def test_language_detector_called() -> None:
    engine = build_engine(FakeVectorStore())
    engine.language_detector = lambda query: "en"  # type: ignore[method-assign]
    response = await engine.answer("q")
    assert response.prompt.context.language == "en"


async def test_context_limit_error_when_budget_tiny() -> None:
    config = RetrievalConfig(
        budget=TokenBudgetConfig(max_prompt_tokens=5, reserved_output_tokens=0),
    )
    store = FakeVectorStore()
    retriever = VectorRetriever(store, fake_embedder([]))
    engine = RetrievalEngine(
        retriever,
        cache=None,
        memory=RollingConversationMemory(),
        config=config,
    )
    with pytest.raises(ContextLimitError):
        await engine.answer("a rather long question about firewall configuration?")


async def test_empty_query_rejected() -> None:
    engine = build_engine(FakeVectorStore())
    with pytest.raises(ValueError):
        await engine.answer("   ")


async def test_aclose_closes_retriever() -> None:
    store = FakeVectorStore()
    closed = False

    async def close() -> None:
        nonlocal closed
        closed = True

    store.aclose = close  # type: ignore[method-assign]
    engine = build_engine(store)
    await engine.aclose()
    assert closed


async def test_optimizer_reduces_oversized_prompt() -> None:
    config = RetrievalConfig(
        budget=TokenBudgetConfig(max_prompt_tokens=120, reserved_output_tokens=0),
    )
    store = FakeVectorStore()
    store.results = [
        SearchResult(
            id=f"d{i}#0",
            score=1.0 - i * 0.01,
            text="long technical paragraph about OpenWrt configuration. " * 8,
            metadata=VectorMetadata(values={"document_id": f"d{i}", "index": 0}),
        )
        for i in range(4)
    ]
    retriever = VectorRetriever(store, fake_embedder([]))
    engine = RetrievalEngine(
        retriever,
        cache=None,
        memory=RollingConversationMemory(),
        config=config,
    )
    response = await engine.answer("describe the firewall configuration in detail")
    assert response.tokens.prompt_tokens <= 120
