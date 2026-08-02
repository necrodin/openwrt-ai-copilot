"""RerankFactory tests: selection, top-n scoring, retries, token usage — all
through mocked transports, no network."""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from providers.embedding import RetryPolicy
from providers.factory import ProviderManager
from providers.nim import NIMProvider
from providers.rerank import NoRerankProviderError, RerankError, RerankFactory
from tests.unit.providers_helpers import make_provider

NO_RETRY = RetryPolicy(max_retries=0)


def _rerank_response(
    *,
    model: str,
    results: list[dict],
    tokens: int = 2,
) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "model": model,
            "results": results,
            "prompt_tokens": tokens,
            "completion_tokens": 0,
        },
    )


def _nim_manager(*, seen: dict[str, Any] | None = None) -> ProviderManager:
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen["calls"] = seen.get("calls", 0) + 1
            seen["payload"] = json.loads(request.content)
        return _rerank_response(
            model="nvidia/rerank",
            results=[
                {"index": 2, "relevance_score": 0.95, "document": "c"},
                {"index": 0, "relevance_score": 0.4, "document": "a"},
            ],
        )

    provider = make_provider(
        NIMProvider,
        handler,
        name="nim",
        model="meta/llama",
        rerank_model="nvidia/rerank",
    )
    return ProviderManager({"nim": provider}, default_provider="nim")


async def test_no_rerank_provider_raises() -> None:
    factory = RerankFactory(ProviderManager({}), retry=NO_RETRY)
    with pytest.raises(NoRerankProviderError):
        await factory.rerank("query", ["a", "b"])


async def test_rerank_returns_ordered_results() -> None:
    seen: dict[str, Any] = {}
    factory = RerankFactory(_nim_manager(seen=seen), retry=NO_RETRY)
    response = await factory.rerank("q", ["a", "b", "c"], top_n=2)
    assert [r.index for r in response.results] == [2, 0]
    assert [round(r.score, 2) for r in response.results] == [0.95, 0.4]
    assert response.model == "nvidia/rerank"
    assert seen["payload"]["query"] == "q"
    assert seen["payload"]["documents"] == ["a", "b", "c"]
    assert seen["payload"]["top_n"] == 2
    assert seen["calls"] == 1


async def test_rerank_empty_documents_makes_no_call() -> None:
    seen: dict[str, Any] = {}
    factory = RerankFactory(_nim_manager(seen=seen), retry=NO_RETRY)
    response = await factory.rerank("q", [])
    assert response.results == []
    assert "calls" not in seen


async def test_rerank_records_token_usage() -> None:
    factory = RerankFactory(_nim_manager(), retry=NO_RETRY)
    await factory.rerank("q", ["a", "b", "c"])
    usage = factory.token_usage()
    assert usage.calls == 1
    assert "rerank" in usage.by_capability


async def test_rerank_providers_lists_static_capability() -> None:
    factory = RerankFactory(_nim_manager(), retry=NO_RETRY)
    assert [p.name for p in factory.rerank_providers()] == ["nim"]


async def test_preferred_provider_routes_rerank() -> None:
    def handler_b(request: httpx.Request) -> httpx.Response:
        return _rerank_response(
            model="rerank-b",
            results=[{"index": 0, "relevance_score": 0.7, "document": "x"}],
        )

    nim = make_provider(
        NIMProvider,
        lambda _: _rerank_response(model="rerank-a", results=[]),
        name="nim",
        model="m",
    )
    other = make_provider(
        NIMProvider,
        handler_b,
        name="other",
        model="m",
        rerank_model="rerank-b",
    )
    manager = ProviderManager({"nim": nim, "other": other}, default_provider="nim")
    factory = RerankFactory(manager, retry=NO_RETRY)
    response = await factory.rerank("q", ["x"], preferred="other")
    assert response.model == "rerank-b"


async def test_rerank_retries_transient_failures() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls <= 2:
            return httpx.Response(503)
        return _rerank_response(
            model="m",
            results=[{"index": 0, "relevance_score": 0.9, "document": "a"}],
        )

    manager = ProviderManager(
        {"nim": make_provider(NIMProvider, handler, name="nim", model="m", rerank_model="rm")},
        default_provider="nim",
    )
    factory = RerankFactory(
        manager,
        retry=RetryPolicy(max_retries=3, base_delay_seconds=0.01, jitter=False),
    )
    response = await factory.rerank("q", ["a"])
    assert response.results[0].index == 0
    assert calls == 3


async def test_rerank_retries_exhausted_raises() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503)

    manager = ProviderManager(
        {"nim": make_provider(NIMProvider, handler, name="nim", model="m", rerank_model="rm")},
        default_provider="nim",
    )
    factory = RerankFactory(manager, retry=RetryPolicy(max_retries=2, jitter=False))
    with pytest.raises(RerankError):
        await factory.rerank("q", ["a"])
    assert calls == 3


async def test_health_reports_rerank_providers() -> None:
    manager = _nim_manager()
    factory = RerankFactory(manager, retry=NO_RETRY)
    assert await factory.health() == {"nim": True}
