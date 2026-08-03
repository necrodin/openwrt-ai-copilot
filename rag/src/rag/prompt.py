"""Prompt rendering + automatic context reduction.

The :class:`DefaultPromptBuilder` is the final pipeline stage — it renders a
:class:`PromptContext` into a ready-for-LLM :class:`PromptRequest` (system +
history + context block + question). The :class:`DefaultPromptOptimizer`
implements automatic context reduction: when the built prompt exceeds the token
budget it drops the lowest-ranked chunks first, then the oldest history, and
finally the context block, before raising :class:`ContextLimitError`.
"""

from __future__ import annotations

import hashlib

from rag.config import TokenBudgetConfig
from rag.errors import ContextLimitError
from rag.models import Message, PromptContext, PromptRequest
from rag.protocols import PromptBuilder, PromptOptimizer
from rag.retriever import VectorRetriever
from rag.tokens import HeuristicTokenEstimator, TokenBudgetManager, TokenEstimator

_DEFAULT_SYSTEM = "You are a helpful assistant grounded in the provided context."


def _checksum(*parts: str) -> str:
    """Deterministic key for the rendered prompt (used by the cache)."""
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def render_system(context: PromptContext, *, include_citations: bool = True) -> str:
    """Build the system message for a context."""
    system = context.system_prompt.strip() or _DEFAULT_SYSTEM
    if include_citations and context.citations:
        system += (
            "\n\nGround your answer strictly in the context above. "
            "Cite sources using [N] markers that match the numbered sources."
        )
    return system


def render_user_message(context: PromptContext) -> str:
    """Render the context block + question into the final user message."""
    parts: list[str] = []
    if context.chunks:
        number = {citation.document_id: citation.number for citation in context.citations}
        lines = ["Context:"]
        for chunk in context.chunks:
            marker = f"[{number.get(chunk.document_id, 0)}]"
            label = f" ({chunk.heading})" if chunk.heading else ""
            lines.append(f"{marker}{label} {chunk.text}")
        parts.append("\n".join(lines))
    parts.append(f"Question: {context.query}")
    return "\n\n".join(parts)


def render_messages(
    context: PromptContext,
    *,
    include_citations: bool = True,
) -> list[Message]:
    """Render system + history + user message for a context."""
    system = render_system(context, include_citations=include_citations)
    messages = [Message(role="system", content=system)]
    messages.extend(context.history)
    messages.append(Message(role="user", content=render_user_message(context)))
    return messages


class DefaultPromptBuilder(PromptBuilder):
    """Render a :class:`PromptContext` into a ready-for-LLM request."""

    def __init__(
        self,
        *,
        system_prompt: str = "",
        include_citations: bool = True,
        reserved_output_tokens: int = 1000,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self.system_prompt = system_prompt
        self.include_citations = include_citations
        self.reserved_output_tokens = reserved_output_tokens
        self.estimator = estimator or HeuristicTokenEstimator()

    def build(self, context: PromptContext) -> PromptRequest:
        context = context.model_copy(deep=True)
        if self.system_prompt:
            context.system_prompt = self.system_prompt
        messages = render_messages(context, include_citations=self.include_citations)
        token_estimate = self.estimator.estimate_messages(messages)
        checksum = _checksum(*(f"{m.role}:{m.content}" for m in messages))
        return PromptRequest(
            query=context.query,
            system=render_system(context, include_citations=self.include_citations),
            messages=messages,
            context=context,
            max_tokens=self.reserved_output_tokens,
            token_estimate=token_estimate,
            checksum=checksum,
        )


class DefaultPromptOptimizer(PromptOptimizer):
    """Automatic context reduction to fit a token budget.

    Reduction order: lowest-ranked chunks first, then oldest history, then the
    entire context block. Raises :class:`ContextLimitError` when even the
    minimal prompt (system + question) cannot fit.
    """

    def __init__(
        self,
        *,
        include_citations: bool = True,
        estimator: TokenEstimator | None = None,
        token_budget: TokenBudgetConfig | None = None,
    ) -> None:
        self.include_citations = include_citations
        budget = token_budget or TokenBudgetConfig()
        self.tokens = TokenBudgetManager(budget, estimator or HeuristicTokenEstimator())

    def optimize(self, request: PromptRequest, max_prompt_tokens: int) -> PromptRequest:
        if request.token_estimate <= max_prompt_tokens:
            return request

        if request.context is None:
            raise ContextLimitError(
                f"prompt is {request.token_estimate} tokens; budget is {max_prompt_tokens}"
            )

        context = request.context.model_copy(deep=True)
        self._trim_chunks(context, max_prompt_tokens)
        self._trim_history(context, max_prompt_tokens)

        if self._estimate(context) > max_prompt_tokens:
            context.chunks = []
            context.documents = []
            context.citations = []

        if self._estimate(context) > max_prompt_tokens:
            raise ContextLimitError(
                f"prompt cannot fit in {max_prompt_tokens} tokens even after reduction"
            )

        context.token_estimate = self._estimate(context)
        builder = DefaultPromptBuilder(
            include_citations=self.include_citations,
            estimator=self.tokens.estimator,
        )
        reduced = builder.build(context)
        return reduced

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _estimate(self, context: PromptContext) -> int:
        return self.tokens.estimate_messages(
            render_messages(context, include_citations=self.include_citations)
        )

    def _trim_chunks(self, context: PromptContext, max_prompt_tokens: int) -> None:
        while context.chunks and self._estimate(context) > max_prompt_tokens:
            context.chunks = context.chunks[:-1]
        context.documents = VectorRetriever.group_by_document(context.chunks)

    def _trim_history(self, context: PromptContext, max_prompt_tokens: int) -> None:
        while context.history and self._estimate(context) > max_prompt_tokens:
            context.history = context.history[1:]


__all__ = [
    "DefaultPromptBuilder",
    "DefaultPromptOptimizer",
    "render_messages",
    "render_system",
    "render_user_message",
]
