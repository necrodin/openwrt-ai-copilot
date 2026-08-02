"""RAGEngine: wire the Retrieval Core to AI providers for grounded chat.

The engine composes the Sprint 9A retrieval pipeline (retrieve -> rerank ->
context -> prompt) with a chat provider facade so a single call produces a
grounded, cited answer. It owns the full turn: build the grounded prompt,
call the provider (streaming or not), record conversation memory, and surface
citations with full provenance.

Nothing here touches a provider SDK directly — the chat and rerank facades are
injected, so tests can substitute fakes and the backend can swap providers via
configuration.
"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from typing import Any

from ai.core.models import ChatMessage, ChatRequest
from rag.ai.config import RAGConfiguration
from rag.ai.errors import NoChatProviderError
from rag.ai.models import RAGCitation, RAGResponse, RAGStreamEvent, RAGUsage
from rag.cache import InMemoryContextCache
from rag.citations import DefaultCitationBuilder
from rag.config import (
    DEFAULT_NAMESPACE,
    CacheConfig,
    CollectionRef,
    ContextConfig,
    MemoryConfig,
    RetrievalConfig,
    TokenBudgetConfig,
)
from rag.engine import RetrievalEngine
from rag.memory import InMemoryMemoryStore, RollingConversationMemory
from rag.models import PromptResponse, RetrievedChunk
from rag.protocols import Reranker, Retriever
from rag.reranker import DummyReranker


class RAGEngine:
    """High-level facade turning a question into a grounded, cited answer.

    Args:
        retriever: the Sprint 9A retriever (e.g. ``VectorRetriever`` with an
            injected embedder).
        configuration: retrieval + provider tuning; a default
            :class:`RAGConfiguration` is used when omitted.
        retrieval_engine: pre-built :class:`RetrievalEngine`; when provided it
            is used as-is (memory/cache/reranker must already be wired).
        reranker: optional reranker; defaults to the deterministic
            :class:`DummyReranker` and is wired into the retrieval engine.
        provider: optional chat provider adapter exposing ``chat()``/``stream()``
            (used when ``chat_caller``/``stream_caller`` are not supplied).
        chat_caller: injected non-streaming caller
            ``(ChatRequest) -> Awaitable[ChatResponse]``.
        stream_caller: injected streaming caller
            ``(ChatRequest) -> AsyncIterator[ChatChunk]``.
    """

    def __init__(
        self,
        retriever: Retriever,
        *,
        configuration: RAGConfiguration | None = None,
        retrieval_engine: RetrievalEngine | None = None,
        reranker: Reranker | None = None,
        provider: Any | None = None,
        chat_caller: Any | None = None,
        stream_caller: Any | None = None,
    ) -> None:
        self.config = configuration or RAGConfiguration()
        self.reranker = reranker or DummyReranker()
        if provider is not None:
            self._chat = provider.chat
            self._stream = provider.stream
        else:
            self._chat = chat_caller
            self._stream = stream_caller

        if retrieval_engine is not None:
            self.retrieval = retrieval_engine
            if self.retrieval.reranker is None:
                self.retrieval.reranker = self.reranker
        else:
            self.retrieval = RetrievalEngine(
                retriever,
                memory=self._build_memory(),
                cache=InMemoryContextCache(CacheConfig(enabled=self.config.use_cache))
                if self.config.use_cache
                else None,
                reranker=self.reranker,
                config=self._retrieval_config(),
            )

    # ------------------------------------------------------------------ #
    # Construction helpers                                               #
    # ------------------------------------------------------------------ #

    def _retrieval_config(self) -> RetrievalConfig:
        return build_retrieval_config(self.config)

    def _build_memory(self) -> RollingConversationMemory | None:
        return build_memory(self.config)

    # ------------------------------------------------------------------ #
    # Retrieval                                                          #
    # ------------------------------------------------------------------ #

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> list[RetrievedChunk]:
        """Retrieve chunks for ``query`` (cached by default)."""
        return await self.retrieval.retrieve(query, top_k=top_k, use_cache=use_cache)

    def citations_for(self, chunks: list[RetrievedChunk]) -> list[RAGCitation]:
        """Turn raw chunks into :class:`RAGCitation` objects."""
        if not chunks:
            return []
        citations = DefaultCitationBuilder().build(chunks)
        return self._citations_from_context(citations, chunks)

    # ------------------------------------------------------------------ #
    # Answering                                                          #
    # ------------------------------------------------------------------ #

    async def answer(
        self,
        query: str,
        *,
        conversation_id: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> RAGResponse:
        """Build the grounded prompt, call the provider, and return the answer."""
        if self._chat is None:
            raise NoChatProviderError(
                "no chat provider is configured for RAG answers; add a chat-capable "
                "provider to providers.yaml"
            )

        started = time.monotonic()
        prompt_response = await self._build_prompt(
            query,
            conversation_id=conversation_id,
            top_k=top_k,
            use_cache=use_cache,
        )
        retrieval_ms = (time.monotonic() - started) * 1000.0

        chat_request = self._chat_request(
            prompt_response,
            model=model,
            temperature=temperature,
        )
        response = await self._chat(chat_request)
        content = response.message.content
        answer = content if isinstance(content, str) else json.dumps(content)

        if conversation_id is not None:
            self.retrieval.complete_turn(conversation_id, answer)

        return self._to_response(
            prompt_response,
            answer,
            conversation_id=conversation_id,
            model=model or response.model,
            retrieval_ms=retrieval_ms,
            chat_usage=response.usage,
        )

    async def stream(
        self,
        query: str,
        *,
        conversation_id: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> AsyncIterator[RAGStreamEvent]:
        """Stream a grounded answer as a sequence of :class:`RAGStreamEvent`."""
        if self._stream is None:
            raise NoChatProviderError("no streaming chat provider is configured for RAG answers")

        yield RAGStreamEvent(type="session", conversation_id=conversation_id or "")
        started = time.monotonic()
        prompt_response = await self._build_prompt(
            query,
            conversation_id=conversation_id,
            top_k=top_k,
            use_cache=use_cache,
        )
        retrieval_ms = (time.monotonic() - started) * 1000.0

        citations = self._citations_for_response(prompt_response)
        yield RAGStreamEvent(
            type="retrieval",
            conversation_id=conversation_id or "",
            citations=citations,
            usage=RAGUsage(
                chunks_retrieved=self._chunk_count(prompt_response),
                cached_chunks=self._cached_chunk_count(prompt_response),
                retrieval_ms=round(retrieval_ms, 3),
            ),
        )

        chat_request = self._chat_request(
            prompt_response,
            model=model,
            temperature=temperature,
        )
        parts: list[str] = []
        streamed_model = model or ""
        yield RAGStreamEvent(
            type="generation_started",
            conversation_id=conversation_id or "",
        )
        try:
            async for chunk in self._stream(chat_request):
                if chunk.delta:
                    parts.append(chunk.delta)
                    streamed_model = streamed_model or chunk.model
                    yield RAGStreamEvent(
                        type="delta",
                        conversation_id=conversation_id or "",
                        content=chunk.delta,
                        model=chunk.model,
                    )
        except Exception as exc:  # noqa: BLE001 - keep the streaming contract
            yield RAGStreamEvent(
                type="error",
                conversation_id=conversation_id or "",
                error=f"AI stream failed: {exc}",
            )
            return

        answer = "".join(parts)
        if conversation_id is not None:
            self.retrieval.complete_turn(conversation_id, answer)

        yield RAGStreamEvent(
            type="citations",
            conversation_id=conversation_id or "",
            citations=citations,
        )
        yield RAGStreamEvent(
            type="done",
            conversation_id=conversation_id or "",
            content=answer,
            citations=citations,
            model=streamed_model,
            usage=RAGUsage(
                chunks_retrieved=self._chunk_count(prompt_response),
                cached_chunks=self._cached_chunk_count(prompt_response),
                retrieval_ms=round(retrieval_ms, 3),
            ),
        )

    async def aclose(self) -> None:
        """Release held resources (retriever)."""
        await self.retrieval.aclose()

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _build_prompt(
        self,
        query: str,
        *,
        conversation_id: str | None,
        top_k: int | None,
        use_cache: bool,
    ) -> PromptResponse:
        return await self.retrieval.answer(
            query,
            conversation_id=conversation_id,
            top_k=top_k,
            use_cache=use_cache,
            remember=True,
        )

    @staticmethod
    def _chat_request(
        prompt_response: PromptResponse,
        *,
        model: str | None,
        temperature: float | None,
    ) -> ChatRequest:
        prompt = prompt_response.prompt
        messages = [
            ChatMessage(role=message.role, content=message.content) for message in prompt.messages
        ]
        return ChatRequest(
            model=model or "",
            messages=messages,
            temperature=temperature,
        )

    def _citations_for_response(
        self,
        prompt_response: PromptResponse,
    ) -> list[RAGCitation]:
        context = prompt_response.prompt.context
        if context is None:
            return []
        return self._citations_from_context(context.citations, context.chunks)

    @staticmethod
    def _citations_from_context(
        citations: list[Any],
        chunks: list[RetrievedChunk],
    ) -> list[RAGCitation]:
        by_id = {chunk.id: chunk for chunk in chunks}
        result: list[RAGCitation] = []
        for citation in citations:
            primary = citation.chunk_ids[0] if citation.chunk_ids else ""
            chunk = by_id.get(primary)
            similarity = chunk.metadata.get("similarity_score", chunk.score) if chunk else 0.0
            rerank_score = chunk.metadata.get("rerank_score") if chunk else None
            confidence = rerank_score if rerank_score is not None else similarity
            result.append(
                RAGCitation(
                    source=citation.source,
                    document=citation.title,
                    section=chunk.heading if chunk else "",
                    chunk_id=primary,
                    similarity_score=round(float(similarity), 6),
                    rerank_score=(
                        round(float(rerank_score), 6) if rerank_score is not None else None
                    ),
                    confidence=round(float(confidence), 6),
                    snippet=citation.snippet or (chunk.text[:160] if chunk else ""),
                )
            )
        return result

    @staticmethod
    def _chunk_count(prompt_response: PromptResponse) -> int:
        context = prompt_response.prompt.context
        return len(context.chunks) if context is not None else 0

    @staticmethod
    def _cached_chunk_count(prompt_response: PromptResponse) -> int:
        if not prompt_response.cached:
            return 0
        return RAGEngine._chunk_count(prompt_response)

    def _to_response(
        self,
        prompt_response: PromptResponse,
        answer: str,
        *,
        conversation_id: str | None,
        model: str,
        retrieval_ms: float,
        chat_usage: Any,
    ) -> RAGResponse:
        return RAGResponse(
            answer=answer,
            conversation_id=conversation_id or "",
            citations=self._citations_for_response(prompt_response),
            model=model,
            usage=RAGUsage(
                prompt_tokens=chat_usage.prompt_tokens,
                completion_tokens=chat_usage.completion_tokens,
                chunks_retrieved=self._chunk_count(prompt_response),
                cached_chunks=self._cached_chunk_count(prompt_response),
                retrieval_ms=round(retrieval_ms, 3),
            ),
            cached=prompt_response.cached,
        )


def build_retrieval_config(configuration: RAGConfiguration) -> RetrievalConfig:
    """Translate a :class:`RAGConfiguration` into a core :class:`RetrievalConfig`.

    Shared by :class:`RAGEngine` and external composers (e.g. the backend
    ``RAGService``) so the retrieval stack is always built identically.
    """
    return RetrievalConfig(
        collections=[
            CollectionRef(
                name=configuration.collection,
                namespace=configuration.namespace or DEFAULT_NAMESPACE,
            )
        ],
        default_top_k=configuration.top_k,
        score_threshold=configuration.score_threshold,
        namespace=configuration.namespace,
        budget=TokenBudgetConfig(max_documents=configuration.max_documents),
        memory=MemoryConfig(
            enabled=configuration.memory_enabled,
            window_size=configuration.memory_window,
        ),
        context=ContextConfig(
            system_prompt=configuration.effective_system_prompt,
            include_citations=True,
        ),
    )


def build_memory(configuration: RAGConfiguration) -> RollingConversationMemory | None:
    """Build the conversation memory for a config (``None`` when disabled)."""
    if not configuration.memory_enabled:
        return None
    return RollingConversationMemory(
        InMemoryMemoryStore(),
        window_size=configuration.memory_window,
    )


__all__ = ["RAGEngine", "build_memory", "build_retrieval_config"]
