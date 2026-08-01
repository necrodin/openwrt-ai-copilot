"""Ollama provider adapter tests (MockTransport, no network)."""

from __future__ import annotations

import json

import httpx
import pytest

from ai.core.errors import UnsupportedCapabilityError
from ai.core.models import ChatMessage, ChatRequest, EmbeddingRequest, RerankRequest
from providers.ollama import OllamaProvider
from tests.unit.providers_helpers import make_provider


def test_capability_defaults() -> None:
    provider = make_provider(OllamaProvider, lambda _: httpx.Response(404))
    assert provider.static_capabilities() == {"chat", "stream"}


async def test_health_true_when_api_reachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/tags"
        return httpx.Response(200, json={"models": []})

    provider = make_provider(OllamaProvider, handler, model="qwen2.5:7b")
    assert await provider.health() is True


async def test_health_false_when_api_unreachable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = make_provider(OllamaProvider, handler)
    assert await provider.health() is False


async def test_chat_uses_default_model_when_not_requested() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "qwen2.5:7b"
        assert body["stream"] is False
        return httpx.Response(
            200,
            json={
                "model": "qwen2.5:7b",
                "message": {"role": "assistant", "content": "Hello!"},
                "done": True,
                "prompt_eval_count": 10,
                "eval_count": 5,
            },
        )

    provider = make_provider(OllamaProvider, handler, model="qwen2.5:7b")
    response = await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="hi")]))
    assert response.message.content == "Hello!"
    assert response.usage.prompt_tokens == 10
    assert response.usage.completion_tokens == 5

    usage = provider.token_usage()
    assert usage.calls == 1
    assert usage.prompt_tokens == 10
    assert usage.completion_tokens == 5
    assert "chat" in usage.by_capability


async def test_stream_collects_deltas_and_records_usage() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        lines = [
            {"model": "qwen2.5:7b", "message": {"content": "Hel"}, "done": False},
            {"model": "qwen2.5:7b", "message": {"content": "lo"}, "done": False},
            {
                "model": "qwen2.5:7b",
                "message": {"content": ""},
                "done": True,
                "prompt_eval_count": 8,
                "eval_count": 3,
            },
        ]
        body = "\n".join(json.dumps(line) for line in lines) + "\n"
        return httpx.Response(200, text=body)

    provider = make_provider(OllamaProvider, handler, model="qwen2.5:7b")
    chunks = [
        chunk
        async for chunk in provider.stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")])
        )
    ]
    assert [c.delta for c in chunks] == ["Hel", "lo", ""]

    usage = provider.token_usage()
    assert usage.calls == 1
    assert usage.prompt_tokens == 8
    assert usage.completion_tokens >= 1
    assert "stream" in usage.by_capability


async def test_embeddings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/embed"
        return httpx.Response(
            200,
            json={
                "model": "nomic-embed-text",
                "embeddings": [[0.1, 0.2], [0.3, 0.4]],
                "prompt_eval_count": 4,
            },
        )

    provider = make_provider(
        OllamaProvider,
        handler,
        model="qwen2.5:7b",
        embed_model="nomic-embed-text",
    )
    response = await provider.embeddings(EmbeddingRequest(inputs=["a", "b"]))
    assert len(response.embeddings) == 2
    assert provider.token_usage().calls == 1


async def test_list_models_maps_ollama_capabilities() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "models": [
                    {"name": "qwen2.5:7b", "capabilities": ["completion"]},
                    {"name": "nomic-embed-text", "capabilities": ["embedding"]},
                    {"name": "llava:13b", "capabilities": ["completion", "vision"]},
                ]
            },
        )

    provider = make_provider(OllamaProvider, handler)
    models = await provider.list_models()
    by_name = {m.id: m.capabilities for m in models}
    assert "chat" in by_name["qwen2.5:7b"]
    assert "embeddings" in by_name["nomic-embed-text"]
    assert "vision" in by_name["llava:13b"]


async def test_rerank_unsupported() -> None:
    provider = make_provider(OllamaProvider, lambda _: httpx.Response(404))
    with pytest.raises(UnsupportedCapabilityError):
        await provider.rerank(RerankRequest(query="q", documents=["d"]))


async def test_stream_error_records_error() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = make_provider(OllamaProvider, handler, model="qwen2.5:7b")
    with pytest.raises(Exception):  # noqa: B017
        async for _ in provider.stream(
            ChatRequest(messages=[ChatMessage(role="user", content="hi")])
        ):
            pass
    assert provider.token_usage().errors == 1
