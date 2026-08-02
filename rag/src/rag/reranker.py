"""Reranking stage for the Retrieval Core.

Reranking re-scores the chunks returned by the vector store against the user's
query so the most relevant context reaches the LLM first. The core only defines
the contract (:class:`Reranker`) plus a deterministic :class:`DummyReranker`
fallback that preserves the vector-store order for providers without a rerank
endpoint — real rerankers (e.g. NVIDIA NIM) are injected by the caller via the
``providers`` package.
"""

from __future__ import annotations

from rag.models import RetrievedChunk
from rag.protocols import Reranker


class DummyReranker(Reranker):
    """Pass-through reranker that preserves the retrieved order.

    Deterministic: chunks keep their original relevance scores and are only
    truncated to ``top_n``. Used when no rerank-capable provider is configured
    so the pipeline stays fully functional.
    """

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        """Return ``chunks`` unchanged (optionally truncated to ``top_n``)."""
        if top_n is not None:
            return chunks[:top_n]
        return chunks


__all__ = ["DummyReranker"]
