"""EmbeddingFactory tests: single/batch embedding, retries, timeouts, health,
token usage — all through mocked transports, no network."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
import pytest

from ai.core.models import Usage
from providers.embedding import (
    EmbeddingError,
    EmbeddingFactory,
    NoEmbeddingProviderError,
    RetryPolicy,
    chunk_texts,
)
from providers.factory import ProviderManager
from providers.ollama import OllamaProvider
from providers.openai import OpenAIProvider
from tests.unit.providers_helpers import make_provider

FAST_RETRY = RetryPolicy(
    max_retries=3, base_delay_seconds=0.01, max_delay_seconds=0.05, jitter=False
)
NO_RETRY = RetryPolicy(max_retries=0)


def _embed_response(model: str, count: int, tokens: int = 1) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "data": [{"embedding": [float(i) + 0.0, float(i) + 1.0]} for i in range(count)],
            "usage": {"prompt_tokens": tokens, "completion_tokens": 0},
        },
    )


def _openai_embed_manager(
    *, seen: dict[str, Any] | None = None, batch_size: int | None = None
) -> ProviderManager:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["calls"] = seen.get("calls", 0) + 1
        body = json.loads(request.content)
        return _embed_response(body["model"], len(body["input"]), len(body["input"]))

    kwargs = {"model": "text-embedding-3-small"}
    if batch_size is not None:
        kwargs["embed_batch_size"] = batch_size
    provider = make_provider(OpenAIProvider, handler, name="embed", **kwargs)
    return ProviderManager({"embed": provider}, default_provider="embed")


def test_chunk_texts() -> None:
    assert chunk_texts(["a", "b", "c"], 2) == [["a", "b"], ["c"]]
    assert chunk_texts(["a"], 2) == [["a"]]
    assert chunk_texts([], 2) == []
    assert chunk_texts(["a", "b"], 0) == [["a"], ["b"]]


async def test_no_provider_raises() -> None:
    factory = EmbeddingFactory(ProviderManager({}), retry=NO_RETRY)
    with pytest.raises(NoEmbeddingProviderError):
        await factory.embed("hello")


async def test_single_embed_returns_vector() -> None:
    seen: dict[str, Any] = {}
    factory = EmbeddingFactory(_openai_embed_manager(seen=seen), retry=NO_RETRY)
    vector = await factory.embed("hello")
    assert vector == [0.0, 1.0]
    assert seen["calls"] == 1
    assert factory.token_usage().calls == 1
    assert "embeddings" in factory.token_usage().by_capability


async def test_batch_embed_splits_into_chunks_and_aggregates() -> None:
    seen: dict[str, Any] = {}
    factory = EmbeddingFactory(_openai_embed_manager(seen=seen), retry=NO_RETRY)
    vectors = await factory.embed_batch(["t1", "t2", "t3", "t4", "t5"], batch_size=2)
    assert len(vectors) == 5
    assert seen["calls"] == 3  # [2, 2, 1]
    usage = factory.token_usage()
    assert usage.calls == 3
    assert usage.prompt_tokens == 5


async def test_batch_respects_provider_batch_size() -> None:
    seen: dict[str, Any] = {}
    factory = EmbeddingFactory(_openai_embed_manager(seen=seen, batch_size=3), retry=NO_RETRY)
    vectors = await factory.embed_batch(["a", "b", "c", "d"])
    assert len(vectors) == 4
    assert seen["calls"] == 2  # [3, 1]


async def test_embed_response_returns_aggregated_usage() -> None:
    seen: dict[str, Any] = {}
    factory = EmbeddingFactory(_openai_embed_manager(seen=seen), retry=NO_RETRY)
    response = await factory.embed_response(["a", "b", "c"], batch_size=2)
    assert len(response.embeddings) == 3
    assert response.usage.prompt_tokens == 3


async def test_empty_batch_makes_no_provider_call() -> None:
    seen: dict[str, Any] = {}
    factory = EmbeddingFactory(_openai_embed_manager(seen=seen), retry=NO_RETRY)
    response = await factory.embed_response([], batch_size=2)
    assert response.embeddings == []
    assert "calls" not in seen


async def test_preferred_provider_is_used() -> None:
    def handler_a(request: httpx.Request) -> httpx.Response:
        return _embed_response("model-a", 1)

    def handler_b(request: httpx.Request) -> httpx.Response:
        return _embed_response("model-b", 1)

    manager = ProviderManager(
        {
            "a": make_provider(OpenAIProvider, handler_a, name="a", model="model-a"),
            "b": make_provider(OpenAIProvider, handler_b, name="b", model="model-b"),
        },
        default_provider="a",
    )
    factory = EmbeddingFactory(manager, retry=NO_RETRY)
    vector = await factory.embed("x", preferred="b")
    assert vector == [0.0, 1.0]
    assert factory._manager.default_name == "a"


async def test_runtime_detection_finds_ollama_with_embed_model() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/tags":
            return httpx.Response(200, json={"models": []})
        body = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "model": body["model"],
                "embeddings": [[0.5, 0.5] for _ in body["input"]],
                "prompt_eval_count": 4,
            },
        )

    provider = make_provider(OllamaProvider, handler, name="ollama", embed_model="nomic-embed-text")
    manager = ProviderManager({"ollama": provider}, default_provider="ollama")
    factory = EmbeddingFactory(manager, retry=NO_RETRY)
    vector = await factory.embed("hello")
    assert vector == [0.5, 0.5]


async def test_retry_succeeds_after_transient_failures() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 2:
            return httpx.Response(503)
        return _embed_response("m", 1)

    manager = ProviderManager(
        {"embed": make_provider(OpenAIProvider, handler, name="embed", model="m")},
        default_provider="embed",
    )
    factory = EmbeddingFactory(manager, retry=FAST_RETRY)
    vector = await factory.embed("hello")
    assert vector == [0.0, 1.0]
    assert calls == 3


async def test_retry_gives_up_after_max_retries() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    manager = ProviderManager(
        {"embed": make_provider(OpenAIProvider, handler, name="embed", model="m")},
        default_provider="embed",
    )
    factory = EmbeddingFactory(manager, retry=RetryPolicy(max_retries=2, jitter=False))
    with pytest.raises(EmbeddingError):
        await factory.embed("hello")
    assert calls == 3


async def test_timeout_raises_embedding_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.2)
        return _embed_response("m", 1)

    provider = make_provider(OpenAIProvider, handler, name="embed", model="m")
    manager = ProviderManager({"embed": provider}, default_provider="embed")
    factory = EmbeddingFactory(manager, retry=NO_RETRY, timeout_seconds=0.05)
    with pytest.raises(EmbeddingError) as excinfo:
        await factory.embed("hello")
    assert isinstance(excinfo.value.__cause__, asyncio.TimeoutError)


async def test_health_reports_all_embedding_providers() -> None:
    ok = make_provider(
        OpenAIProvider,
        lambda _: httpx.Response(200, json={"data": [{"id": "m"}]}),
        name="ok",
        model="m",
    )
    down = make_provider(OpenAIProvider, lambda _: httpx.Response(503), name="down")
    manager = ProviderManager({"ok": ok, "down": down})
    factory = EmbeddingFactory(manager, retry=NO_RETRY)
    assert await factory.health() == {"ok": True, "down": False}


async def test_health_preferred_provider() -> None:
    ok = make_provider(
        OpenAIProvider,
        lambda _: httpx.Response(200, json={"data": [{"id": "m"}]}),
        name="ok",
        model="m",
    )
    factory = EmbeddingFactory(ProviderManager({"ok": ok}, default_provider="ok"), retry=NO_RETRY)
    assert await factory.health(preferred="ok") == {"ok": True}


def test_embedding_providers_lists_static_only() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _embed_response("m", 1)

    openai = make_provider(OpenAIProvider, handler, name="openai", model="m")
    ollama = make_provider(OllamaProvider, lambda _: httpx.Response(404), name="ollama")
    manager = ProviderManager({"openai": openai, "ollama": ollama})
    factory = EmbeddingFactory(manager, retry=NO_RETRY)
    names = [p.name for p in factory.embedding_providers()]
    assert names == ["openai"]


async def test_token_usage_aggregates_across_providers() -> None:
    seen_a: dict[str, Any] = {}
    seen_b: dict[str, Any] = {}
    factory_a = EmbeddingFactory(_openai_embed_manager(seen=seen_a), retry=NO_RETRY)
    factory_b = EmbeddingFactory(_openai_embed_manager(seen=seen_b), retry=NO_RETRY)
    await factory_a.embed_batch(["a", "b"], batch_size=1)
    await factory_b.embed("single")

    manager = ProviderManager(
        {
            "a": factory_a._manager.providers["embed"],
            "b": factory_b._manager.providers["embed"],
        },
        default_provider="a",
    )
    combined = EmbeddingFactory(manager, retry=NO_RETRY)
    usage = combined.token_usage()
    assert usage.calls == 3
    assert usage.prompt_tokens == 3
    assert usage.by_capability["embeddings"].prompt_tokens == 3
    assert isinstance(usage.by_capability["embeddings"], Usage)
