"""RAG integration layer tests: grounded answers, citations, streaming,
conversation memory, context expansion, embedding cache, rerank bridge, and the
core rerank hook — all through injected fakes, no network."""

from __future__ import annotations

import pytest

from ai.core.models import (
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    RerankResponse,
    RerankResult,
    Usage,
)
from providers.factory import ProviderManager
from providers.nim import NIMProvider
from rag.ai import (
    CachedEmbedder,
    EmbeddingCache,
    ProviderReranker,
    RAGConfiguration,
    RAGEngine,
    RAGSession,
    build_reranker,
)
from rag.ai.errors import NoChatProviderError
from rag.config import RetrievalConfig
from rag.engine import RetrievalEngine
from rag.models import RetrievedChunk
from rag.protocols import Reranker
from rag.reranker import DummyReranker
from tests.unit.providers_helpers import make_provider


def make_chunk(
    index: int,
    document_id: str,
    text: str,
    *,
    heading: str = "",
    source: str = "knowledge/docs/x.md",
    title: str = "x.md",
) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{document_id}#{index}",
        document_id=document_id,
        index=index,
        text=text,
        heading=heading,
        score=round(0.95 - 0.05 * index, 3),
        metadata={
            "document_id": document_id,
            "index": index,
            "heading": heading,
            "source": source,
            "title": title,
            "reference": "",
            "format": "md",
            "language": "en",
            "checksum": "",
            "version": 1,
        },
    )


class FakeRetriever:
    """Retrieve from a fixed chunk list (no embedding, no vector store)."""

    def __init__(self, chunks: list[RetrievedChunk]) -> None:
        self._chunks = chunks

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: list | None = None,
        namespace: str | None = None,
    ) -> list[RetrievedChunk]:
        if top_k is None:
            return list(self._chunks)
        return list(self._chunks[:top_k])

    async def aclose(self) -> None:
        return None


def capturing_chat(seen: dict):
    async def caller(request: ChatRequest) -> ChatResponse:
        seen["request"] = request
        return ChatResponse(
            model="test-model",
            message=ChatMessage(role="assistant", content="**Grounded** answer [1]"),
            usage=Usage(prompt_tokens=12, completion_tokens=5),
        )

    return caller


async def fake_stream(request: ChatRequest):
    for piece in ["Grounded ", "**answer**"]:
        yield ChatChunk(model="test-model", delta=piece)


def make_engine(
    chunks: list[RetrievedChunk],
    *,
    chat_caller=None,
    stream_caller=None,
    config: RAGConfiguration | None = None,
) -> RAGEngine:
    return RAGEngine(
        FakeRetriever(chunks),
        configuration=config or RAGConfiguration(top_k=4, max_documents=3),
        chat_caller=chat_caller,
        stream_caller=stream_caller,
    )


# ------------------------------------------------------------------ #
# Configuration                                                      #
# ------------------------------------------------------------------ #


def test_rag_configuration_from_dict_and_defaults() -> None:
    config = RAGConfiguration.from_dict(
        {
            "top_k": 5,
            "max_documents": 3,
            "rerank_provider": "nim",
            "temperature": 0.3,
            "vector_dimensions": 256,
        }
    )
    assert config.top_k == 5
    assert config.max_documents == 3
    assert config.rerank_provider == "nim"
    assert config.temperature == 0.3
    assert config.vector_dimensions == 256
    assert config.rerank_model is None
    assert "grounded" in config.effective_system_prompt.lower()


def test_rag_configuration_validates_range() -> None:
    with pytest.raises(ValueError):
        RAGConfiguration(top_k=0)


# ------------------------------------------------------------------ #
# RAGEngine: answer                                                  #
# ------------------------------------------------------------------ #


async def test_rag_engine_answer_injects_context_and_citations() -> None:
    chunks = [
        make_chunk(
            0,
            "wireguard",
            "WireGuard uses Curve25519 for key exchange.",
            heading="Crypto",
            source="knowledge/docs/wireguard.md",
            title="wireguard.md",
        )
    ]
    seen: dict = {}
    engine = make_engine(chunks, chat_caller=capturing_chat(seen))
    response = await engine.answer("how does wireguard work?", conversation_id="c1")

    assert response.answer == "**Grounded** answer [1]"
    assert response.model == "test-model"
    assert response.conversation_id == "c1"
    assert response.cached is False
    assert len(response.citations) == 1
    citation = response.citations[0]
    assert citation.source == "knowledge/docs/wireguard.md"
    assert citation.document == "wireguard.md"
    assert citation.section == "Crypto"
    assert citation.chunk_id == "wireguard#0"
    assert citation.similarity_score == 0.95
    assert citation.rerank_score is None
    assert citation.confidence == 0.95
    assert response.usage.chunks_retrieved == 1

    request = seen["request"]
    assert request.messages[-1].role == "user"
    assert "Context:" in request.messages[-1].content
    assert "WireGuard uses Curve25519" in request.messages[-1].content
    assert "Question:" in request.messages[-1].content


async def test_rag_engine_no_chat_provider_raises() -> None:
    engine = make_engine([make_chunk(0, "a", "text")])
    with pytest.raises(NoChatProviderError):
        await engine.answer("q", conversation_id="c1")


async def test_rag_engine_stream_emits_delta_citations_done() -> None:
    chunks = [make_chunk(0, "wireguard", "WireGuard text.", heading="Crypto")]
    engine = make_engine(chunks, stream_caller=fake_stream)
    events = [event async for event in engine.stream("q", conversation_id="c3")]
    assert [event.type for event in events] == [
        "session",
        "retrieval",
        "generation_started",
        "delta",
        "delta",
        "citations",
        "done",
    ]
    deltas = [event.content for event in events if event.type == "delta"]
    assert deltas == ["Grounded ", "**answer**"]
    assert events[-1].content == "Grounded **answer**"
    retrieval = next(event for event in events if event.type == "retrieval")
    assert len(retrieval.citations) == 1
    assert retrieval.citations[0].chunk_id == "wireguard#0"
    assert len(events[-2].citations) == 1
    assert events[-2].citations[0].chunk_id == "wireguard#0"


async def test_rag_engine_stream_error_event() -> None:
    async def failing_stream(request: ChatRequest):
        raise RuntimeError("boom")
        yield  # pragma: no cover - makes this an async generator

    engine = make_engine([], stream_caller=failing_stream)
    events = [event async for event in engine.stream("q", conversation_id="c4")]
    assert [event.type for event in events] == [
        "session",
        "retrieval",
        "generation_started",
        "error",
    ]
    assert "boom" in events[-1].error


async def test_rag_engine_conversation_memory_feeds_history() -> None:
    seen: dict = {}
    engine = make_engine(
        [make_chunk(0, "wireguard", "WireGuard text.")],
        chat_caller=capturing_chat(seen),
    )
    await engine.answer("first", conversation_id="c2")
    await engine.answer("second", conversation_id="c2")
    roles = [message.role for message in seen["request"].messages]
    assert roles == ["system", "user", "assistant", "user"]
    assert seen["request"].messages[1].content == "first"


# ------------------------------------------------------------------ #
# RAGSession                                                         #
# ------------------------------------------------------------------ #


async def test_rag_session_generates_conversation_id() -> None:
    engine = make_engine([], chat_caller=capturing_chat({}))
    session = RAGSession(engine)
    assert session.conversation_id
    assert len(session.conversation_id) > 8


async def test_rag_session_memory_persists_across_answers() -> None:
    seen: dict = {}
    engine = make_engine(
        [make_chunk(0, "wireguard", "WireGuard text.")],
        chat_caller=capturing_chat(seen),
    )
    session = RAGSession(engine)
    await session.answer("first")
    await session.answer("second")
    roles = [message.role for message in seen["request"].messages]
    assert roles == ["system", "user", "assistant", "user"]


async def test_rag_session_expand_context_returns_novel_citations() -> None:
    chunks = [make_chunk(index, f"doc{index}", f"text {index}") for index in range(4)]
    engine = make_engine(chunks, chat_caller=capturing_chat({}))
    session = RAGSession(engine, conversation_id="s1")

    first = await session.answer("question")
    first_ids = {citation.chunk_id for citation in first.citations}
    assert len(first_ids) == 3  # 4 chunks, capped to max_documents=3

    novel = await session.expand_context("question")
    novel_ids = {citation.chunk_id for citation in novel}
    assert novel_ids
    assert novel_ids.isdisjoint(first_ids)


async def test_rag_session_expand_context_disabled() -> None:
    engine = make_engine(
        [make_chunk(0, "a", "text")],
        chat_caller=capturing_chat({}),
        config=RAGConfiguration(top_k=2, context_expansion=False),
    )
    session = RAGSession(engine, conversation_id="s1")
    assert await session.expand_context("q") == []


async def test_rag_session_reset_clears_memory() -> None:
    seen: dict = {}
    engine = make_engine(
        [make_chunk(0, "wireguard", "WireGuard text.")],
        chat_caller=capturing_chat(seen),
    )
    session = RAGSession(engine)
    await session.answer("first")
    session.reset()
    await session.answer("again")
    roles = [message.role for message in seen["request"].messages]
    assert roles == ["system", "user"]


# ------------------------------------------------------------------ #
# Embedding cache                                                    #
# ------------------------------------------------------------------ #


def test_embedding_cache_hit_and_miss() -> None:
    cache = EmbeddingCache()
    assert cache.get("hello") is None
    cache.put("hello", [1.0, 2.0])
    assert cache.get("hello") == [1.0, 2.0]
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1
    assert stats["entries"] == 1


def test_embedding_cache_clear() -> None:
    cache = EmbeddingCache()
    cache.put("a", [1.0])
    cache.clear()
    assert cache.get("a") is None
    assert cache.stats()["entries"] == 0


async def test_cached_embedder_reuses_vectors() -> None:
    calls = 0

    class FakeFactory:
        async def embed(self, text, **kwargs):
            nonlocal calls
            calls += 1
            return [float(len(text)), 0.0]

    embedder = CachedEmbedder(FakeFactory())
    assert await embedder("abc") == [3.0, 0.0]
    assert await embedder("abc") == [3.0, 0.0]
    assert calls == 1
    assert await embedder("abcd") == [4.0, 0.0]
    assert calls == 2


# ------------------------------------------------------------------ #
# Rerank bridge + core hook                                          #
# ------------------------------------------------------------------ #


async def test_dummy_reranker_preserves_order_and_truncates() -> None:
    chunks = [make_chunk(0, "a", "t0"), make_chunk(1, "b", "t1"), make_chunk(2, "c", "t2")]
    reranker = DummyReranker()
    result = await reranker.rerank("q", chunks, top_n=2)
    assert [chunk.id for chunk in result] == ["a#0", "b#1"]


class ReverseReranker(Reranker):
    async def rerank(self, query, chunks, *, top_n=None):
        ordered = list(reversed(chunks))
        return ordered[:top_n] if top_n is not None else ordered


async def test_retrieval_engine_applies_reranker_hook() -> None:
    chunks = [make_chunk(0, "a", "t0"), make_chunk(1, "b", "t1"), make_chunk(2, "c", "t2")]
    engine = RetrievalEngine(
        FakeRetriever(chunks),
        reranker=ReverseReranker(),
        config=RetrievalConfig(default_top_k=3),
    )
    retrieved = await engine.retrieve("q")
    assert [chunk.id for chunk in retrieved] == ["c#2", "b#1", "a#0"]
    assert retrieved[0].rank == 1
    assert retrieved[-1].rank == 3


async def test_provider_reranker_maps_scores() -> None:
    class FakeRerankFactory:
        async def rerank(self, query, documents, *, top_n=None, preferred=None, model=None):
            return RerankResponse(
                model="m",
                results=[
                    RerankResult(index=1, document=documents[1], score=0.9),
                    RerankResult(index=0, document=documents[0], score=0.3),
                ],
            )

    chunks = [make_chunk(0, "a", "t0"), make_chunk(1, "b", "t1")]
    reranker = ProviderReranker(FakeRerankFactory())
    result = await reranker.rerank("q", chunks, top_n=2)
    assert [chunk.id for chunk in result] == ["b#1", "a#0"]
    assert round(result[0].score, 6) == 0.9
    assert round(result[1].score, 6) == 0.3
    # similarity is preserved alongside the rerank score for citations
    assert round(result[0].metadata["similarity_score"], 3) == 0.9
    assert result[0].metadata["rerank_score"] == 0.9
    assert result[1].metadata["rerank_score"] == 0.3


async def test_provider_reranker_falls_back_when_factory_fails() -> None:
    class FailingRerankFactory:
        async def rerank(self, query, documents, *, top_n=None, preferred=None, model=None):
            raise RuntimeError("provider down")

    chunks = [make_chunk(0, "a", "t0"), make_chunk(1, "b", "t1")]
    reranker = ProviderReranker(FailingRerankFactory())
    result = await reranker.rerank("q", chunks, top_n=1)
    assert [chunk.id for chunk in result] == ["a#0"]


def test_build_reranker_dummy_when_not_configured() -> None:
    reranker = build_reranker(ProviderManager({}), RAGConfiguration())
    assert isinstance(reranker, DummyReranker)


def test_build_reranker_provider_when_configured() -> None:
    def handler(request):
        return __import__("httpx").Response(200, json={"model": "m", "results": []})

    nim = make_provider(
        NIMProvider,
        handler,
        name="nim",
        model="m",
        rerank_model="nvidia/rerank",
    )
    config = RAGConfiguration(rerank_provider="nim", rerank_model="nvidia/rerank")
    reranker = build_reranker(ProviderManager({"nim": nim}), config)
    assert isinstance(reranker, ProviderReranker)
