"""Error hierarchy for the Retrieval Core.

Callers can catch :class:`RetrievalError` to handle any failure uniformly;
more specific subclasses exist so the exact failure (embedding, context
overflow, cache) can be surfaced to the user or the monitoring layer.
"""

from __future__ import annotations


class RetrievalError(Exception):
    """Base class for all Retrieval Core errors."""


class RetrieverError(RetrievalError):
    """A retriever could not produce results (search/merge/dedupe failure)."""


class EmbeddingError(RetrieverError):
    """The query could not be embedded (embedder failure or missing embedder)."""


class CollectionError(RetrieverError):
    """A configured collection could not be searched."""


class ContextLimitError(RetrievalError):
    """The assembled prompt exceeds the configured context budget.

    Raised after automatic reduction has already run and the minimum viable
    prompt still cannot fit.
    """


__all__ = [
    "CollectionError",
    "ContextLimitError",
    "EmbeddingError",
    "RetrievalError",
    "RetrieverError",
]
