"""RetrievalEngine: orchestrates the full pipeline into an LLM-ready prompt.

``Question -> Embedding -> VectorStore -> Merge Results -> Remove Duplicates
-> Context Builder -> Prompt Builder -> Ready For LLM``

The engine wires the swappable components together, applies caching and the
token budget, and records conversation history. It never touches a provider
SDK or an LLM — the returned :class:`PromptResponse` is what a later sprint
hands to the AI layer.
"""

from __future__ import annotations

import hashlib

from rag.config import RetrievalConfig
from rag.context import DefaultContextBuilder
from rag.errors import ContextLimitError
from rag.models import ConversationState, PromptContext, PromptResponse, RetrievedChunk, TokenCounts
from rag.prompt import DefaultPromptBuilder, DefaultPromptOptimizer
from rag.protocols import (
    ContextBuilder,
    ContextCache,
    ConversationMemory,
    LanguageDetector,
    PromptBuilder,
    PromptOptimizer,
    Reranker,
    Retriever,
)
from rag.retriever import VectorRetriever
from rag.tokens import TokenBudgetManager


class RetrievalEngine:
    """High-level facade for the retrieval pipeline."""

    def __init__(
        self,
        retriever: Retriever,
        *,
        context_builder: ContextBuilder | None = None,
        prompt_builder: PromptBuilder | None = None,
        optimizer: PromptOptimizer | None = None,
        token_budget: TokenBudgetManager | None = None,
        memory: ConversationMemory | None = None,
        cache: ContextCache | None = None,
        language_detector: LanguageDetector = None,
        reranker: Reranker | None = None,
        config: RetrievalConfig | None = None,
    ) -> None:
        self.retriever = retriever
        self.config = config or RetrievalConfig()
        self.context_builder = context_builder or DefaultContextBuilder(
            max_documents=self.config.budget.max_documents,
            max_chunks_per_document=self.config.budget.max_chunks_per_document,
            include_citations=self.config.context.include_citations,
        )
        self.prompt_builder = prompt_builder or DefaultPromptBuilder(
            system_prompt=self.config.context.system_prompt,
            include_citations=self.config.context.include_citations,
            reserved_output_tokens=self.config.budget.reserved_output_tokens,
        )
        self.optimizer = optimizer or DefaultPromptOptimizer(
            include_citations=self.config.context.include_citations,
            token_budget=self.config.budget,
        )
        self.tokens = token_budget or TokenBudgetManager(self.config.budget)
        self.memory = memory
        self.cache = cache
        self.language_detector = language_detector
        self.reranker = reranker

    # ------------------------------------------------------------------ #
    # Retrieval                                                          #
    # ------------------------------------------------------------------ #

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: list | None = None,
        namespace: str | None = None,
        use_cache: bool = True,
    ) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for ``query`` (cached by default)."""
        use_cache = use_cache and self.cache is not None
        key = self._retrieval_key(query, top_k, namespace, filters) if use_cache else ""
        if use_cache:
            cached = await self.cache.get_retrieval(key)
            if cached is not None:
                return cached

        chunks = await self.retriever.retrieve(
            query,
            top_k=top_k,
            filters=filters,
            namespace=namespace,
        )
        if self.reranker is not None:
            chunks = await self.reranker.rerank(
                query,
                chunks,
                top_n=top_k or self.config.default_top_k,
            )
            for position, chunk in enumerate(chunks, start=1):
                chunk.rank = position
        if use_cache:
            await self.cache.set_retrieval(key, chunks)
        return chunks

    # ------------------------------------------------------------------ #
    # Prompt building                                                    #
    # ------------------------------------------------------------------ #

    async def answer(
        self,
        query: str,
        *,
        conversation_id: str | None = None,
        top_k: int | None = None,
        filters: list | None = None,
        namespace: str | None = None,
        use_cache: bool = True,
        remember: bool = True,
    ) -> PromptResponse:
        """Run the pipeline and return an LLM-ready :class:`PromptResponse`."""
        if not query or not query.strip():
            raise ValueError("query must be a non-empty string")

        history = await self._history_for(conversation_id)
        history_sig = self._history_signature(history)

        cache_on = use_cache and self.cache is not None and conversation_id is None
        prompt_key = ""
        if cache_on:
            prompt_key = self._prompt_key(query, top_k, namespace, history_sig)
            cached = await self.cache.get_prompt(prompt_key)
            if cached is not None:
                return cached.model_copy(update={"cached": True})

        chunks = await self.retrieve(
            query,
            top_k=top_k,
            filters=filters,
            namespace=namespace,
            use_cache=use_cache,
        )

        context = self._build_context(query, chunks, history)
        prompt = self.prompt_builder.build(context)
        if prompt.token_estimate > self.tokens.budget.max_prompt_tokens:
            prompt = self.optimizer.optimize(prompt, self.tokens.budget.max_prompt_tokens)
        if prompt.token_estimate > self.tokens.budget.max_prompt_tokens:
            raise ContextLimitError(
                f"prompt is {prompt.token_estimate} tokens; budget is "
                f"{self.tokens.budget.max_prompt_tokens}"
            )

        if remember and conversation_id is not None and self.memory is not None:
            self.memory.add(conversation_id, "user", query)

        response = PromptResponse(
            request_id=prompt.request_id,
            query=query,
            prompt=prompt,
            tokens=TokenCounts(
                prompt_tokens=prompt.token_estimate,
                context_tokens=context.token_estimate,
                history_tokens=self.tokens.estimate_messages(context.history),
                max_tokens=self.tokens.budget.reserved_output_tokens,
            ),
            cached=False,
            cache_key=prompt_key,
        )
        if cache_on and prompt_key:
            await self.cache.set_prompt(prompt_key, response)
        return response

    def complete_turn(
        self,
        conversation_id: str,
        assistant_text: str,
    ) -> ConversationState | None:
        """Record the assistant answer (used once an LLM sprint exists)."""
        if self.memory is None:
            return None
        return self.memory.add(conversation_id, "assistant", assistant_text)

    async def aclose(self) -> None:
        """Release held resources (retriever)."""
        await self.retriever.aclose()

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _history_for(self, conversation_id: str | None) -> list:
        if conversation_id is None or self.memory is None:
            return []
        reserved = self.tokens.budget.reserved_output_tokens
        return self.memory.history(
            conversation_id,
            max_tokens=self.tokens.history_budget(reserved),
        )

    def _build_context(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        history: list,
    ) -> PromptContext:
        language = ""
        if self.language_detector is not None:
            language = self.language_detector(query) or ""
        return self.context_builder.build(
            query,
            chunks,
            history=history,
            language=language,
            system_prompt=self.config.context.system_prompt,
        )

    def _collection_signature(self) -> str:
        if not isinstance(self.retriever, VectorRetriever):
            return ""
        parts = []
        for ref in self.retriever.collections:
            parts.append(f"{ref.name}:{ref.namespace}:{ref.weight}")
        return ";".join(parts)

    def _retrieval_key(
        self,
        query: str,
        top_k: int | None,
        namespace: str | None,
        filters: list | None,
    ) -> str:
        return self.cache.checksum_key(
            "retrieval",
            self._collection_signature(),
            str(top_k or self.config.default_top_k),
            namespace or "",
            repr(filters or []),
            query,
        )

    @staticmethod
    def _history_signature(history: list) -> str:
        if not history:
            return ""
        parts = [f"{m.role}:{m.content}" for m in history]
        return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()

    def _prompt_key(
        self,
        query: str,
        top_k: int | None,
        namespace: str | None,
        history_sig: str,
    ) -> str:
        return self.cache.checksum_key(
            "prompt",
            query,
            str(top_k or self.config.default_top_k),
            namespace or "",
            history_sig,
        )


__all__ = ["RetrievalEngine"]
