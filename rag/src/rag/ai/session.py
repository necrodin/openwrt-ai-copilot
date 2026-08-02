"""RAGSession: a per-conversation chat session over a :class:`RAGEngine`.

A session owns one conversation: it generates and remembers its id, drives
memory (the retrieval engine records user/assistant turns), and can expand the
retrieved context on demand without repeating chunks the user has already seen.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from uuid import uuid4

from rag.ai.engine import RAGEngine
from rag.ai.models import RAGCitation, RAGResponse, RAGStreamEvent


class RAGSession:
    """Stateful chat session bound to a single conversation."""

    def __init__(
        self,
        engine: RAGEngine,
        *,
        conversation_id: str | None = None,
    ) -> None:
        self.engine = engine
        self.conversation_id = conversation_id or str(uuid4())
        self._cited_chunk_ids: set[str] = set()

    # ------------------------------------------------------------------ #
    # Chat                                                               #
    # ------------------------------------------------------------------ #

    async def answer(
        self,
        message: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> RAGResponse:
        """Answer ``message`` in this conversation (non-streaming)."""
        response = await self.engine.answer(
            message,
            conversation_id=self.conversation_id,
            model=model,
            temperature=temperature,
            top_k=top_k,
            use_cache=use_cache,
        )
        self._record(response.citations)
        return response

    async def stream(
        self,
        message: str,
        *,
        model: str | None = None,
        temperature: float | None = None,
        top_k: int | None = None,
        use_cache: bool = True,
    ) -> AsyncIterator[RAGStreamEvent]:
        """Stream ``message`` as a sequence of :class:`RAGStreamEvent`."""
        async for event in self.engine.stream(
            message,
            conversation_id=self.conversation_id,
            model=model,
            temperature=temperature,
            top_k=top_k,
            use_cache=use_cache,
        ):
            if event.citations:
                self._record(event.citations)
            yield event

    # ------------------------------------------------------------------ #
    # Context expansion                                                  #
    # ------------------------------------------------------------------ #

    async def expand_context(
        self,
        query: str,
        *,
        top_k: int | None = None,
    ) -> list[RAGCitation]:
        """Retrieve broader context for ``query`` beyond the default breadth.

        Returns citations for chunks the conversation has not cited yet, so
        "give me more detail" surfaces fresh sources instead of repeating the
        ones already injected. Honors ``RAGConfiguration.context_expansion``;
        returns an empty list when expansion is disabled.
        """
        if not self.engine.config.context_expansion:
            return []
        expanded = top_k or max(self.engine.config.top_k * 2, self.engine.config.top_k + 2)
        chunks = await self.engine.retrieve(query, top_k=expanded)
        citations = self.engine.citations_for(chunks)
        novel = [
            citation for citation in citations if citation.chunk_id not in self._cited_chunk_ids
        ]
        self._record(novel)
        return novel

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def reset(self) -> None:
        """Forget cited-chunk tracking and reset conversation memory."""
        self._cited_chunk_ids.clear()
        memory = self.engine.retrieval.memory
        if memory is not None:
            memory.reset(self.conversation_id)

    async def aclose(self) -> None:
        """Release the engine's held resources."""
        await self.engine.aclose()

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _record(self, citations: list[RAGCitation]) -> None:
        for citation in citations:
            if citation.chunk_id:
                self._cited_chunk_ids.add(citation.chunk_id)


__all__ = ["RAGSession"]
