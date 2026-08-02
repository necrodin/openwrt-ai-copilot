"""InMemoryContextCache tests: TTL, checksum keys, eviction, invalidation."""

from __future__ import annotations

from rag.cache import InMemoryContextCache
from rag.config import CacheConfig
from rag.models import Message, PromptRequest, PromptResponse, RetrievedChunk


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def make_chunks(n: int = 2) -> list[RetrievedChunk]:
    return [
        RetrievedChunk(id=f"d{i}#0", document_id=f"d{i}", index=0, text=f"text {i}")
        for i in range(n)
    ]


def make_response(query: str = "q") -> PromptResponse:
    request = PromptRequest(query=query, messages=[Message(role="user", content="payload")])
    return PromptResponse(request_id="r1", query=query, prompt=request)


async def test_retrieval_roundtrip() -> None:
    cache = InMemoryContextCache()
    chunks = make_chunks()
    await cache.set_retrieval("key", chunks)
    assert await cache.get_retrieval("key") == chunks
    assert await cache.get_retrieval("missing") is None


async def test_prompt_roundtrip() -> None:
    cache = InMemoryContextCache()
    response = make_response()
    await cache.set_prompt("key", response)
    assert await cache.get_prompt("key") == response


async def test_retrieval_ttl_expiry() -> None:
    clock = FakeClock()
    cache = InMemoryContextCache(CacheConfig(retrieval_ttl_seconds=10), clock=clock)
    await cache.set_retrieval("key", make_chunks())
    clock.now += 11
    assert await cache.get_retrieval("key") is None


async def test_prompt_ttl_expiry() -> None:
    clock = FakeClock()
    cache = InMemoryContextCache(CacheConfig(prompt_ttl_seconds=5), clock=clock)
    await cache.set_prompt("key", make_response())
    clock.now += 6
    assert await cache.get_prompt("key") is None


async def test_custom_ttl_override() -> None:
    clock = FakeClock()
    cache = InMemoryContextCache(CacheConfig(retrieval_ttl_seconds=1), clock=clock)
    await cache.set_retrieval("key", make_chunks(), ttl_seconds=100)
    clock.now += 50
    assert await cache.get_retrieval("key") is not None


async def test_disabled_cache_never_stores() -> None:
    cache = InMemoryContextCache(CacheConfig(enabled=False))
    await cache.set_retrieval("key", make_chunks())
    await cache.set_prompt("key", make_response())
    assert await cache.get_retrieval("key") is None
    assert await cache.get_prompt("key") is None


async def test_checksum_key_deterministic_and_unique() -> None:
    checksum = InMemoryContextCache.checksum_key
    assert checksum("a", "b") == checksum("a", "b")
    assert checksum("a", "b") != checksum("a", "c")


async def test_invalidate_by_prefix() -> None:
    cache = InMemoryContextCache()
    await cache.set_retrieval("conv-1:q1", make_chunks())
    await cache.set_retrieval("conv-2:q1", make_chunks())
    await cache.set_prompt("prompt:conv-1", make_response())
    cache.invalidate("conv-1")
    assert await cache.get_retrieval("conv-1:q1") is None
    assert await cache.get_retrieval("conv-2:q1") is not None
    assert await cache.get_prompt("prompt:conv-1") is not None


async def test_clear_drops_everything() -> None:
    cache = InMemoryContextCache()
    await cache.set_retrieval("k", make_chunks())
    await cache.set_prompt("k", make_response())
    cache.clear()
    assert await cache.get_retrieval("k") is None
    assert await cache.get_prompt("k") is None


async def test_stats_counts_hits_and_misses() -> None:
    cache = InMemoryContextCache()
    await cache.set_retrieval("k", make_chunks())
    await cache.get_retrieval("k")
    await cache.get_retrieval("missing")
    await cache.get_retrieval("missing")
    stats = cache.stats()
    assert stats["hits"]["retrieval"] == 1
    assert stats["misses"]["retrieval"] == 2


async def test_eviction_respects_max_entries() -> None:
    cache = InMemoryContextCache(CacheConfig(max_entries=2))
    for i in range(5):
        await cache.set_retrieval(f"key-{i}", make_chunks())
    stats = cache.stats()
    assert stats["retrieval_entries"] == 2
    assert await cache.get_retrieval("key-0") is None
    assert await cache.get_retrieval("key-4") is not None
