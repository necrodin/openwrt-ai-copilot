"""NVIDIA NIM provider adapter tests (rerank via /v1/rerank)."""

from __future__ import annotations

import json

import httpx

from ai.core.models import RerankRequest
from providers.nim import NIMProvider
from tests.unit.providers_helpers import make_provider


def test_capability_defaults_include_rerank() -> None:
    provider = make_provider(NIMProvider, lambda _: httpx.Response(404))
    caps = provider.static_capabilities()
    assert "chat" in caps
    assert "rerank" in caps


async def test_rerank() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/rerank"
        body = json.loads(request.content)
        assert body["model"] == "nvidia/llama-3.2-nv-rerankqa-1b-v2"
        assert body["query"] == "cats"
        return httpx.Response(
            200,
            json={
                "model": "nvidia/llama-3.2-nv-rerankqa-1b-v2",
                "results": [
                    {"index": 1, "relevance_score": 0.9},
                    {"index": 0, "relevance_score": 0.2},
                ],
                "prompt_tokens": 20,
                "completion_tokens": 5,
            },
        )

    provider = make_provider(
        NIMProvider,
        handler,
        model="meta/llama-3.3-70b-instruct",
        rerank_model="nvidia/llama-3.2-nv-rerankqa-1b-v2",
    )
    response = await provider.rerank(
        RerankRequest(query="cats", documents=["dogs", "cats and kittens"])
    )
    assert [r.index for r in response.results] == [1, 0]
    assert response.results[0].document == "cats and kittens"
    assert response.results[0].score == 0.9

    usage = provider.token_usage()
    assert usage.calls == 1
    assert "rerank" in usage.by_capability


async def test_rerank_infers_document_from_response() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "model": "m",
                "results": [{"index": 0, "score": 0.5, "document": "inline doc"}],
            },
        )

    provider = make_provider(NIMProvider, handler, model="m", rerank_model="m")
    response = await provider.rerank(RerankRequest(query="q", documents=["fallback"]))
    assert response.results[0].document == "inline doc"
