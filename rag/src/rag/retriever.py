"""Retrieval implementation: embed -> search -> merge -> dedupe -> rank.

The :class:`VectorRetriever` is the "VectorStore" stage of the pipeline. It
depends only on the ``vectorstore`` interface and an injected embedder
callable, so it works with any store backend and any embedding provider.

Search strategy:

1. Embed the query with the injected embedder.
2. Search every configured collection concurrently.
3. Normalise cosine scores to 0..1 per collection (min-max) and weight them.
4. Merge across collections, de-duplicating by chunk id and (optionally) by
   canonical text, keeping the highest score.
5. Apply the score threshold, sort best-first, and cap at ``top_k``.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Sequence
from typing import Any

from rag.config import DEFAULT_COLLECTION, CollectionRef
from rag.errors import CollectionError, EmbeddingError, RetrieverError
from rag.models import RetrievedChunk, RetrievedDocument
from rag.protocols import Embedder, Retriever
from vectorstore.models import DEFAULT_NAMESPACE, MetadataFilter, SearchRequest, SearchResult
from vectorstore.protocols import VectorStore

#: Metadata keys a future knowledge->vectorstore bridge is expected to write.
_META_DOCUMENT_ID = "document_id"
_META_INDEX = "index"
_META_HEADING = "heading"
_META_TITLE = "title"
_META_SOURCE = "source"
_META_REFERENCE = "reference"
_META_FORMAT = "format"
_META_LANGUAGE = "language"
_META_CHECKSUM = "checksum"
_META_VERSION = "version"

_METADATA_KEYS = (
    _META_DOCUMENT_ID,
    _META_INDEX,
    _META_HEADING,
    _META_TITLE,
    _META_SOURCE,
    _META_REFERENCE,
    _META_FORMAT,
    _META_LANGUAGE,
    _META_CHECKSUM,
    _META_VERSION,
)


def _text_key(text: str) -> str:
    """Canonical key for content-based de-duplication."""
    normalized = " ".join(text.split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _normalize_scores(scores: Sequence[float]) -> list[float]:
    """Min-max normalise to 0..1; all-equal scores become 1.0."""
    if not scores:
        return []
    low, high = min(scores), max(scores)
    if high == low:
        return [1.0] * len(scores)
    return [(score - low) / (high - low) for score in scores]


class VectorRetriever(Retriever):
    """Retrieve chunks from a ``vectorstore`` backend given an embedder."""

    def __init__(
        self,
        vector_store: VectorStore,
        embedder: Embedder | None = None,
        *,
        collections: Sequence[CollectionRef] | None = None,
        default_top_k: int = 8,
        score_threshold: float | None = None,
        deduplicate_by_text: bool = True,
    ) -> None:
        self.vector_store = vector_store
        self._embedder = embedder
        self.collections = list(collections or [CollectionRef(name=DEFAULT_COLLECTION)])
        self.default_top_k = max(1, default_top_k)
        self.score_threshold = score_threshold
        self.deduplicate_by_text = deduplicate_by_text

    def set_embedder(self, embedder: Embedder | None) -> None:
        """Swap the embedder at runtime (keeps the retriever provider-agnostic)."""
        self._embedder = embedder

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: list[MetadataFilter] | None = None,
        namespace: str | None = None,
    ) -> list[RetrievedChunk]:
        """Embed the query and return the ``top_k`` most relevant chunks."""
        if not query or not query.strip():
            raise RetrieverError("query must be a non-empty string")

        k = max(1, top_k or self.default_top_k)
        query_vector = await self._embed_query(query)

        per_collection = await self._search_all(query_vector, k, filters, namespace)
        merged = self._merge(per_collection)
        merged = self._dedupe(merged)
        chunks = [self._to_chunk(result, score) for result, score in merged]
        chunks = [chunk for chunk in chunks if self._passes_threshold(chunk)]
        chunks.sort(key=lambda chunk: chunk.score, reverse=True)
        for rank, chunk in enumerate(chunks[:k], start=1):
            chunk.rank = rank
        return chunks[:k]

    async def retrieve_documents(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: list[MetadataFilter] | None = None,
        namespace: str | None = None,
    ) -> list[RetrievedDocument]:
        """Retrieve chunks and group them into :class:`RetrievedDocument` objects."""
        chunks = await self.retrieve(
            query,
            top_k=top_k,
            filters=filters,
            namespace=namespace,
        )
        return self.group_by_document(chunks)

    @staticmethod
    def group_by_document(
        chunks: list[RetrievedChunk],
    ) -> list[RetrievedDocument]:
        """Group a ranked chunk list into documents, preserving rank order."""
        documents: dict[str, RetrievedDocument] = {}
        order: list[str] = []
        for chunk in chunks:
            if chunk.document_id not in documents:
                documents[chunk.document_id] = RetrievedDocument(
                    document_id=chunk.document_id,
                    title=chunk.metadata.get(_META_TITLE) or "",
                    source=chunk.metadata.get(_META_SOURCE) or "",
                    reference=chunk.metadata.get(_META_REFERENCE) or "",
                    format=chunk.metadata.get(_META_FORMAT) or "",
                    language=chunk.metadata.get(_META_LANGUAGE) or "",
                    checksum=chunk.metadata.get(_META_CHECKSUM) or "",
                    version=int(chunk.metadata.get(_META_VERSION) or 1),
                )
                order.append(chunk.document_id)
            documents[chunk.document_id].chunks.append(chunk)
            documents[chunk.document_id].best_score = max(
                documents[chunk.document_id].best_score, chunk.score
            )
        return [documents[document_id] for document_id in order]

    async def aclose(self) -> None:
        """Close the underlying vector store."""
        await self.vector_store.aclose()

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _embed_query(self, query: str) -> list[float]:
        if self._embedder is None:
            raise EmbeddingError(
                "no embedder configured; supply one to VectorRetriever or call set_embedder()"
            )
        try:
            vector = await self._embedder(query)
        except Exception as exc:  # pragma: no cover - provider failure
            raise EmbeddingError(f"embedding query failed: {exc}") from exc
        if not vector:
            raise EmbeddingError("embedder returned an empty vector")
        return vector

    async def _search_all(
        self,
        query_vector: list[float],
        top_k: int,
        filters: list[MetadataFilter] | None,
        namespace: str | None,
    ) -> list[list[SearchResult]]:
        """Concurrently search every configured collection."""
        candidate_k = max(top_k, top_k * len(self.collections))
        tasks = [
            self._search_collection(
                collection,
                query_vector,
                candidate_k,
                filters,
                namespace,
            )
            for collection in self.collections
        ]
        results = await asyncio.gather(*tasks)
        return list(results)

    async def _search_collection(
        self,
        collection: CollectionRef,
        query_vector: list[float],
        candidate_k: int,
        filters: list[MetadataFilter] | None,
        namespace: str | None,
    ) -> list[SearchResult]:
        request = SearchRequest(
            query_vector=query_vector,
            top_k=candidate_k,
            filters=list(filters or []),
        )
        effective_namespace = namespace or collection.namespace
        try:
            return await self.vector_store.search(
                collection.name,
                request,
                namespace=effective_namespace,
            )
        except Exception as exc:
            raise CollectionError(
                f"searching collection {collection.name!r} "
                f"(namespace {effective_namespace!r}) failed: {exc}"
            ) from exc

    def _merge(self, per_collection: list[list[SearchResult]]) -> list[tuple[SearchResult, float]]:
        """Merge + weight + de-duplicate-by-id across collections."""
        merged: dict[str, tuple[SearchResult, float]] = {}
        for results, collection in zip(per_collection, self.collections, strict=True):
            scores = _normalize_scores([r.score for r in results])
            for result, normalized in zip(results, scores, strict=True):
                score = normalized * collection.weight
                existing = merged.get(result.id)
                if existing is None or score > existing[1]:
                    merged[result.id] = (result, score)
        return list(merged.values())

    def _dedupe(self, merged: list[tuple[SearchResult, float]]) -> list[tuple[SearchResult, float]]:
        if not self.deduplicate_by_text:
            return merged
        seen: set[str] = set()
        deduped: list[tuple[SearchResult, float]] = []
        for result, score in sorted(merged, key=lambda item: item[1], reverse=True):
            key = _text_key(result.text or "")
            if key in seen:
                continue
            seen.add(key)
            deduped.append((result, score))
        return deduped

    def _to_chunk(self, result: SearchResult, score: float) -> RetrievedChunk:
        metadata = result.metadata.to_dict()
        document_id, index = self._document_identity(result.id, metadata)
        return RetrievedChunk(
            id=result.id,
            document_id=document_id,
            index=index,
            text=result.text,
            heading=metadata.get(_META_HEADING, ""),
            score=round(score, 6),
            metadata={
                key: value
                for key, value in metadata.items()
                if key in _METADATA_KEYS and value is not None
            },
        )

    @staticmethod
    def _document_identity(chunk_id: str, metadata: dict[str, Any]) -> tuple[str, int]:
        document_id = metadata.get(_META_DOCUMENT_ID, "")
        index = metadata.get(_META_INDEX)
        if document_id and isinstance(index, int):
            return document_id, index
        parsed = RetrievedChunk.parse_id(chunk_id)
        if parsed is not None:
            return parsed
        return chunk_id, 0

    def _passes_threshold(self, chunk: RetrievedChunk) -> bool:
        return self.score_threshold is None or chunk.score >= self.score_threshold


__all__ = ["DEFAULT_NAMESPACE", "VectorRetriever"]
