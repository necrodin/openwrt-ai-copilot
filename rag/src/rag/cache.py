"""Context cache: retrieval results + built prompts, TTL + checksum keyed.

The :class:`InMemoryContextCache` stores (a) retrieval results keyed by the
query + collection identity and (b) built prompts keyed by conversation +
query, so the exact same question asked again within the TTL skips embedding,
search, and prompt rendering entirely. Pure in-memory for now; the
:class:`ContextCache` protocol allows a durable backend later.
"""

from __future__ import annotations

import hashlib
import threading
import time
from typing import Any

from rag.config import CacheConfig
from rag.models import PromptResponse, RetrievedChunk
from rag.protocols import ContextCache


def _checksum(*parts: str) -> str:
    payload = "\x1f".join(parts).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


class InMemoryContextCache(ContextCache):
    """TTL-bounded in-memory cache for retrieval and prompt stages."""

    def __init__(
        self,
        config: CacheConfig | None = None,
        *,
        clock: Any | None = None,
    ) -> None:
        self.config = config or CacheConfig()
        self._clock = clock or time.monotonic
        self._retrieval: dict[str, tuple[float, list[RetrievedChunk]]] = {}
        self._prompt: dict[str, tuple[float, PromptResponse]] = {}
        self._hits = {"retrieval": 0, "prompt": 0}
        self._misses = {"retrieval": 0, "prompt": 0}
        self._lock = threading.RLock()

    # ------------------------------------------------------------------ #
    # Retrieval                                                          #
    # ------------------------------------------------------------------ #

    async def get_retrieval(self, key: str) -> list[RetrievedChunk] | None:
        if not self.config.enabled:
            return None
        with self._lock:
            self._prune("retrieval")
            entry = self._retrieval.get(key)
            if entry is None:
                self._misses["retrieval"] += 1
                return None
            expires, chunks = entry
            if expires <= self._clock():
                self._retrieval.pop(key, None)
                self._misses["retrieval"] += 1
                return None
            self._hits["retrieval"] += 1
            return list(chunks)

    async def set_retrieval(
        self,
        key: str,
        chunks: list[RetrievedChunk],
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        if not self.config.enabled:
            return
        ttl = ttl_seconds if ttl_seconds is not None else self.config.retrieval_ttl_seconds
        with self._lock:
            self._retrieval[key] = (self._clock() + ttl, list(chunks))
            self._evict("retrieval")

    # ------------------------------------------------------------------ #
    # Prompt                                                             #
    # ------------------------------------------------------------------ #

    async def get_prompt(self, key: str) -> PromptResponse | None:
        if not self.config.enabled:
            return None
        with self._lock:
            self._prune("prompt")
            entry = self._prompt.get(key)
            if entry is None:
                self._misses["prompt"] += 1
                return None
            expires, response = entry
            if expires <= self._clock():
                self._prompt.pop(key, None)
                self._misses["prompt"] += 1
                return None
            self._hits["prompt"] += 1
            return response

    async def set_prompt(
        self,
        key: str,
        response: PromptResponse,
        *,
        ttl_seconds: int | None = None,
    ) -> None:
        if not self.config.enabled:
            return
        ttl = ttl_seconds if ttl_seconds is not None else self.config.prompt_ttl_seconds
        with self._lock:
            self._prompt[key] = (self._clock() + ttl, response)
            self._evict("prompt")

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def invalidate(self, key_prefix: str = "") -> None:
        """Drop entries whose key starts with ``key_prefix`` (all if empty)."""
        with self._lock:
            if not key_prefix:
                self.clear()
                return
            for bucket in (self._retrieval, self._prompt):
                for key in list(bucket):
                    if key.startswith(key_prefix):
                        bucket.pop(key, None)

    def clear(self) -> None:
        with self._lock:
            self._retrieval.clear()
            self._prompt.clear()

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "retrieval_entries": len(self._retrieval),
                "prompt_entries": len(self._prompt),
                "hits": dict(self._hits),
                "misses": dict(self._misses),
                "enabled": self.config.enabled,
            }

    @staticmethod
    def checksum_key(*parts: str) -> str:
        return _checksum(*parts)

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _prune(self, bucket: str) -> None:
        store = self._retrieval if bucket == "retrieval" else self._prompt
        now = self._clock()
        expired = [key for key, (expires, _) in store.items() if expires <= now]
        for key in expired:
            store.pop(key, None)

    def _evict(self, bucket: str) -> None:
        store = self._retrieval if bucket == "retrieval" else self._prompt
        limit = self.config.max_entries
        while len(store) > limit:
            oldest = next(iter(store))
            store.pop(oldest, None)


__all__ = ["InMemoryContextCache"]
