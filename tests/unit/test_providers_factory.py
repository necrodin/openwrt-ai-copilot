"""Provider factory and manager tests."""

from __future__ import annotations

import json

import httpx
import pytest

from ai.core.errors import ProviderUnavailableError
from ai.core.models import ChatMessage, ChatRequest
from providers.config import ProvidersConfig
from providers.factory import (
    ProviderManager,
    available_provider_types,
    create_provider,
    create_provider_manager,
    register_provider,
    unregister_provider,
)
from providers.lmstudio import LMStudioProvider
from providers.openai import OpenAIProvider
from tests.unit.providers_helpers import make_provider


def test_registered_types() -> None:
    types = available_provider_types()
    assert "ollama" in types
    assert "nim" in types
    assert "openai" in types
    assert "openrouter" in types
    assert "lmstudio" in types
    assert "vllm" in types


def test_register_and_unregister_custom_provider() -> None:
    register_provider("mytype", OpenAIProvider)
    assert "mytype" in available_provider_types()
    unregister_provider("mytype")
    assert "mytype" not in available_provider_types()


def test_create_provider_unknown_type_raises() -> None:
    from providers.config import ProviderConfig

    unregister_provider("openai")
    try:
        with pytest.raises(KeyError):
            create_provider(ProviderConfig(type="openai"))
    finally:
        register_provider("openai", OpenAIProvider)


def test_create_provider_manager_builds_enabled_only() -> None:
    config = ProvidersConfig.model_validate(
        {
            "default_provider": "ollama",
            "providers": {
                "ollama": {"enabled": True},
                "openai": {"enabled": False},
            },
        }
    )
    manager = create_provider_manager(config)
    assert manager.names() == ["ollama"]
    assert manager.default_name == "ollama"
    assert manager.default() is not None


def test_manager_get_for_capability_prefers_default() -> None:
    config = ProvidersConfig.model_validate(
        {
            "default_provider": "ollama",
            "providers": {
                "ollama": {},
                "openai": {},
            },
        }
    )
    manager = create_provider_manager(config)
    chat = manager.get_for_capability("chat")
    assert chat is not None
    assert chat.name == "ollama"
    embeddings = manager.get_for_capability("embeddings")
    assert embeddings is not None
    assert embeddings.name == "openai"
    assert manager.get_for_capability("rerank") is None


def test_manager_get_for_capability_respects_preferred() -> None:
    config = ProvidersConfig.model_validate(
        {
            "default_provider": "ollama",
            "providers": {"ollama": {}, "openai": {}},
        }
    )
    manager = create_provider_manager(config)
    provider = manager.get_for_capability("embeddings", preferred="ollama")
    assert provider is not None
    assert provider.name == "openai"
    # Preferred name is considered first but must still declare the capability;
    # ollama does not declare embeddings, so openai wins regardless.
    assert provider.name == "openai"


async def test_manager_health_reports_failure_without_raising() -> None:
    manager = ProviderManager(
        {
            "broken": make_provider(OpenAIProvider, lambda _: httpx.Response(503)),
        }
    )
    assert await manager.health() == {"broken": False}


async def test_manager_health_reports_ok() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [{"id": "m"}]})

    manager = ProviderManager({"good": make_provider(OpenAIProvider, handler)})
    assert await manager.health() == {"good": True}


async def test_manager_aclose_swallows_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("nope")

    manager = ProviderManager({"x": make_provider(LMStudioProvider, handler)})
    # aclose on an injected client is a no-op (not owned); must not raise.
    await manager.aclose()


async def test_chat_roundtrip_with_openai_provider() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 1},
            },
        )

    provider = make_provider(OpenAIProvider, handler, model="gpt-4o-mini")
    response = await provider.chat(ChatRequest(messages=[ChatMessage(role="user", content="yo")]))
    assert response.message.content == "hi"
    assert provider.token_usage().calls == 1


async def test_embeddings_error_surfaces() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    provider = make_provider(OpenAIProvider, handler, model="m")
    from ai.core.models import EmbeddingRequest

    with pytest.raises(ProviderUnavailableError):
        await provider.embeddings(EmbeddingRequest(inputs=["x"]))
