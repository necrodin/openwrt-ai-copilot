"""Bridge a ``providers`` rerank factory into the core :class:`rag.protocols.Reranker` contract.

The provider factory returns a :class:`ai.core.models.RerankResponse` whose
results reference the input documents by index; this bridge maps those scores
back onto the retrieved chunks and falls back to the deterministic dummy
reranker when no rerank-capable provider is configured.

The bridge keeps the original vector-store similarity alongside the rerank score
(under ``metadata``) so citations can expose both numbers.
"""

from __future__ import annotations

from rag.models import RetrievedChunk
from rag.protocols import Reranker
from rag.reranker import DummyReranker

#: Metadata key carrying the pre-rerank similarity (set only when reranked).
_SIMILARITY_KEY = "similarity_score"
#: Metadata key carrying the provider rerank score (set only when reranked).
_RERANK_KEY = "rerank_score"


class ProviderReranker(Reranker):
    """Score retrieved chunks through a :class:`providers.RerankFactory`.

    Args:
        factory: the provider-backed rerank facade. ``None`` (or a factory that
            cannot resolve a rerank provider) degrades to ``fallback``.
        preferred: provider name preference passed to the factory.
        model: rerank model override passed to the factory.
        fallback: used when no rerank provider is available; defaults to
            :class:`DummyReranker` (preserve vector-store order).
    """

    def __init__(
        self,
        factory,
        *,
        preferred: str | None = None,
        model: str | None = None,
        fallback: Reranker | None = None,
    ) -> None:
        self._factory = factory
        self._preferred = preferred
        self._model = model
        self._fallback = fallback or DummyReranker()

    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        if self._factory is None or not chunks:
            return await self._fallback.rerank(query, chunks, top_n=top_n)

        try:
            response = await self._factory.rerank(
                query,
                [chunk.text for chunk in chunks],
                top_n=top_n,
                preferred=self._preferred,
                model=self._model,
            )
        except Exception:  # noqa: BLE001 - degrade gracefully to vector-store order
            return await self._fallback.rerank(query, chunks, top_n=top_n)

        if not response.results:
            return await self._fallback.rerank(query, chunks, top_n=top_n)

        by_index = dict(enumerate(chunks))
        ordered: list[RetrievedChunk] = []
        for result in response.results:
            chunk = by_index.get(result.index)
            if chunk is None:
                continue
            rerank_score = round(max(0.0, min(1.0, result.score)), 6)
            ordered.append(
                chunk.model_copy(
                    update={
                        "score": rerank_score,
                        "metadata": {
                            **chunk.metadata,
                            _SIMILARITY_KEY: chunk.score,
                            _RERANK_KEY: rerank_score,
                        },
                    }
                )
            )
        if not ordered:
            return await self._fallback.rerank(query, chunks, top_n=top_n)
        return ordered


def build_reranker(
    manager,
    configuration,
) -> Reranker:
    """Build the reranker for a provider manager + RAG configuration.

    Returns a :class:`DummyReranker` (deterministic vector-store order) unless a
    rerank provider or model is configured, in which case a
    :class:`ProviderReranker` over a fresh :class:`providers.RerankFactory` is
    returned.
    """
    if not (configuration.rerank_provider or configuration.rerank_model):
        return DummyReranker()

    from providers.rerank import RerankFactory

    factory = RerankFactory(manager)
    return ProviderReranker(
        factory,
        preferred=configuration.rerank_provider,
        model=configuration.rerank_model,
    )


__all__ = ["ProviderReranker", "build_reranker"]
