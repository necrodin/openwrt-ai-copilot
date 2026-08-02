"""NVIDIA NV-Embed provider tests (MockTransport, no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from ai.core.models import EmbeddingRequest
from providers.factory import available_provider_types
from providers.nv_embed import DEFAULT_NV_EMBED_MODEL, NVEmbedProvider
from tests.unit.providers_helpers import make_provider


def _embed_handler(
    *,
    model: str,
    vector: list[float],
    input_type: str | None = None,
    models: bool = True,
):
    def handler(request: httpx.Request) -> httpx.Response:
        if models and request.url.path == "/v1/models":
            return httpx.Response(200, json={"data": [{"id": model}]})
        assert request.url.path == "/v1/embeddings"
        body = json.loads(request.content)
        assert body["model"] == model
        if input_type is not None:
            assert body.get("input_type") == input_type
        return httpx.Response(
            200,
            json={
                "model": model,
                "data": [{"embedding": vector}],
                "usage": {"total_tokens": 8},
            },
        )

    return handler


def test_capability_defaults_embeddings_only() -> None:
    provider = make_provider(NVEmbedProvider, lambda _: httpx.Response(404))
    assert provider.static_capabilities() == {"embeddings"}


def test_registered_as_builtin_type() -> None:
    assert "nvembed" in available_provider_types()


async def test_embeddings_uses_default_model() -> None:
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=DEFAULT_NV_EMBED_MODEL, vector=[0.1, 0.2]),
    )
    response = await provider.embeddings(EmbeddingRequest(inputs=["hello"]))
    assert response.model == DEFAULT_NV_EMBED_MODEL
    assert response.embeddings[0].embedding == [0.1, 0.2]
    # total_tokens fallback lands in prompt_tokens
    assert response.usage.prompt_tokens == 8
    assert provider.token_usage().calls == 1
    assert "embeddings" in provider.token_usage().by_capability


async def test_embeddings_resolves_configured_embed_model() -> None:
    model = "nvidia/NV-Embed-v2"
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=model, vector=[0.5]),
        embed_model=model,
    )
    response = await provider.embeddings(EmbeddingRequest(inputs=["x"]))
    assert response.model == model


async def test_embeddings_requested_model_wins() -> None:
    requested = "custom/embed-model"
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=requested, vector=[0.5]),
        embed_model="nvidia/NV-Embed-v2",
    )
    response = await provider.embeddings(EmbeddingRequest(model=requested, inputs=["x"]))
    assert response.model == requested


async def test_embeddings_sends_input_type_when_requested() -> None:
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=DEFAULT_NV_EMBED_MODEL, vector=[0.5], input_type="query"),
    )
    response = await provider.embeddings(
        EmbeddingRequest(inputs=["what is nat"], input_type="query")
    )
    assert len(response.embeddings) == 1


async def test_embeddings_normalizes_vectors() -> None:
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=DEFAULT_NV_EMBED_MODEL, vector=[3.0, 4.0]),
    )
    response = await provider.embeddings(EmbeddingRequest(inputs=["x"], normalize=True))
    assert response.embeddings[0].embedding == [0.6, 0.8]


async def test_embeddings_without_normalize_keeps_raw_vector() -> None:
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=DEFAULT_NV_EMBED_MODEL, vector=[3.0, 4.0]),
    )
    response = await provider.embeddings(EmbeddingRequest(inputs=["x"]))
    assert response.embeddings[0].embedding == [3.0, 4.0]


async def test_dimensions_from_config() -> None:
    provider = make_provider(
        NVEmbedProvider,
        lambda _: httpx.Response(404),
        embed_dimensions=1024,
    )
    assert provider.dimensions() == 1024


async def test_health_true_when_embeddings_reachable() -> None:
    provider = make_provider(
        NVEmbedProvider,
        _embed_handler(model=DEFAULT_NV_EMBED_MODEL, vector=[0.1]),
    )
    assert await provider.health() is True


async def test_health_false_when_unreachable() -> None:
    provider = make_provider(NVEmbedProvider, lambda _: httpx.Response(503))
    assert await provider.health() is False


async def test_embeddings_error_surfaces() -> None:
    provider = make_provider(NVEmbedProvider, lambda _: httpx.Response(404))
    with pytest.raises(Exception):  # noqa: B017 - error surfaced to caller
        await provider.embeddings(EmbeddingRequest(inputs=["x"]))
