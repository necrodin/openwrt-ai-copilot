"""Embedding cache shared across queries.

Retrieval embeddings are deterministic, so caching the query vector avoids
re-hitting the embedding provider for repeat/near-repeat questions. The cache is
an LRU-ish bounded dict keyed by a checksum of the text; it reuses the same
hashed-key approach as :class:`rag.cache.InMemoryContextCache`.
"""

from __future__ import annotations

import hashlib
import threading
from collections.abc import Callable
from typing import Any

Embedder = Callable[[str], Any]


def _key(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EmbeddingCache:
    """Bounded in-memory cache for text -> embedding vector."""

    def __init__(self, max_entries: int = 4096) -> None:
        self.max_entries = max(1, max_entries)
        self._store: dict[str, list[float]] = {}
        self._lock = threading.RLock()
        self._hits = 0
        self._misses = 0

    def get(self, text: str) -> list[float] | None:
        with self._lock:
            vector = self._store.get(_key(text))
            if vector is None:
                self._misses += 1
                return None
            self._hits += 1
            return list(vector)

    def put(self, text: str, vector: list[float]) -> None:
        if not vector:
            return
        with self._lock:
            key = _key(text)
            if key in self._store:
                return
            if len(self._store) >= self.max_entries:
                self._store.pop(next(iter(self._store)), None)
            self._store[key] = list(vector)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()
            self._hits = 0
            self._misses = 0

    def stats(self) -> dict[str, int]:
        with self._lock:
            return {"entries": len(self._store), "hits": self._hits, "misses": self._misses}


class CachedEmbedder:
    """Wrap an :class:`providers.EmbeddingFactory` with a shared vector cache.

    Satisfies the ``rag.protocols.Embedder`` callable contract (``text ->
    vector``) so it plugs straight into :class:`rag.retriever.VectorRetriever`.
    """

    def __init__(
        self,
        factory: Any,
        cache: EmbeddingCache | None = None,
        *,
        preferred: str | None = None,
        model: str | None = None,
        input_type: str | None = None,
        normalize: bool = False,
    ) -> None:
        self._factory = factory
        self._cache = cache or EmbeddingCache()
        self._preferred = preferred
        self._model = model
        self._input_type = input_type
        self._normalize = normalize

    async def __call__(self, text: str) -> list[float]:
        if not text:
            return []
        cached = self._cache.get(text)
        if cached is not None:
            return cached
        vector = await self._factory.embed(
            text,
            preferred=self._preferred,
            model=self._model,
            input_type=self._input_type,
            normalize=self._normalize,
        )
        self._cache.put(text, vector)
        return vector

    def invalidate(self) -> None:
        """Drop cached vectors (e.g. after knowledge ingestion)."""
        self._cache.clear()


__all__ = ["CachedEmbedder", "EmbeddingCache"]
