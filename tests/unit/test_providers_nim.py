"""NVIDIA NIM provider adapter tests (rerank + embeddings)."""

from __future__ import annotations

import json

import httpx

from ai.core.models import EmbeddingRequest, RerankRequest
from providers.nim import NIMProvider
from tests.unit.providers_helpers import make_provider


def test_capability_defaults_include_rerank() -> None:
    provider = make_provider(NIMProvider, lambda _: httpx.Response(404))
    caps = provider.static_capabilities()
    assert "chat" in caps
    assert "rerank" in caps
    assert "embeddings" in caps


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


async def test_embeddings_uses_embed_model_and_total_tokens_fallback() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.content)
        assert body["model"] == "nvidia/NV-Embed-QA-Mistral-4B"
        return httpx.Response(
            200,
            json={
                "model": "nvidia/NV-Embed-QA-Mistral-4B",
                "data": [{"index": 0, "embedding": [3.0, 4.0]}],
                "usage": {"total_tokens": 8},
            },
        )

    provider = make_provider(
        NIMProvider,
        handler,
        model="meta/llama-3.3-70b-instruct",
        embed_model="nvidia/NV-Embed-QA-Mistral-4B",
        embed_dimensions=1024,
    )
    response = await provider.embeddings(
        EmbeddingRequest(model="nvidia/NV-Embed-QA-Mistral-4B", inputs=["hello"])
    )
    assert response.embeddings[0].embedding == [3.0, 4.0]
    assert response.usage.prompt_tokens == 8

    usage = provider.token_usage()
    assert usage.calls == 1
    assert "embeddings" in usage.by_capability
