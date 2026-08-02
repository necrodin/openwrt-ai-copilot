"""Context assembly: group, cap, cite, and enrich retrieved chunks.

The :class:`DefaultContextBuilder` is the "Context Builder" stage. It takes the
retriever's ranked chunk list plus conversation history and produces a
:class:`PromptContext` that respects the configured document/chunk/history caps
and carries the citations the prompt builder will reproduce.
"""

from __future__ import annotations

from rag.citations import DefaultCitationBuilder
from rag.config import TokenBudgetConfig
from rag.models import Message, PromptContext, RetrievedChunk
from rag.protocols import ContextBuilder
from rag.retriever import VectorRetriever
from rag.tokens import TokenBudgetManager


class DefaultContextBuilder(ContextBuilder):
    """Group + cap + cite + attach history for the prompt builder."""

    def __init__(
        self,
        *,
        max_documents: int | None = None,
        max_chunks_per_document: int | None = None,
        include_citations: bool = True,
        citation_builder: DefaultCitationBuilder | None = None,
        token_budget: TokenBudgetConfig | None = None,
    ) -> None:
        self.max_documents = max_documents
        self.max_chunks_per_document = max_chunks_per_document
        self.include_citations = include_citations
        self.citation_builder = citation_builder or DefaultCitationBuilder()
        self.tokens = TokenBudgetManager(token_budget or TokenBudgetConfig())

    def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        history: list[Message] | None = None,
        language: str = "",
        system_prompt: str = "",
    ) -> PromptContext:
        documents = VectorRetriever.group_by_document(chunks)
        documents = self._cap_documents(documents)
        documents = self._cap_chunks_per_document(documents)

        flat: list[RetrievedChunk] = []
        for document in documents:
            flat.extend(document.chunks)

        citations = self.citation_builder.build(flat) if self.include_citations else []
        trimmed_history = self._trim_history(history or [])

        context = PromptContext(
            query=query,
            chunks=flat,
            documents=documents,
            citations=citations,
            history=trimmed_history,
            language=language,
            system_prompt=system_prompt,
        )
        context.token_estimate = self._estimate_context(context)
        return context

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _cap_documents(self, documents: list) -> list:
        if self.max_documents is None or len(documents) <= self.max_documents:
            return documents
        return documents[: self.max_documents]

    def _cap_chunks_per_document(self, documents: list) -> list:
        if self.max_chunks_per_document is None:
            return documents
        for document in documents:
            document.chunks = document.chunks[: self.max_chunks_per_document]
        return documents

    def _trim_history(self, history: list[Message]) -> list[Message]:
        """Keep the most recent messages that fit in the history token budget."""
        budget = self.tokens.history_budget()
        if budget <= 0:
            return []
        kept: list[Message] = []
        total = 0
        for message in reversed(history):
            cost = self.tokens.estimate(message.content)
            if total + cost > budget:
                break
            kept.append(message)
            total += cost
        kept.reverse()
        return kept

    def _estimate_context(self, context: PromptContext) -> int:
        body = context.query + "\n" + context.system_prompt
        body += "\n".join(chunk.text for chunk in context.chunks)
        body += "\n".join(message.content for message in context.history)
        return self.tokens.estimate(body)


__all__ = ["DefaultContextBuilder"]
