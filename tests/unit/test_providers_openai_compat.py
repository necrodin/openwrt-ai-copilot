"""OpenAI-compatible wire protocol tests."""

from __future__ import annotations

import json

import httpx

from ai.core.models import (
    ChatMessage,
    ChatRequest,
    ContentPart,
    EmbeddingRequest,
)
from providers.openai_compat import (
    messages_to_wire,
    parse_chat_response,
    parts_to_wire,
    request_chat,
    request_chat_stream,
    request_embeddings,
    request_models,
)
from providers.transport import ProviderTransport
from tests.unit.providers_helpers import make_mock_client


def test_parts_to_wire_text_and_image() -> None:
    assert parts_to_wire(ContentPart(type="text", text="hi")) == {
        "type": "text",
        "text": "hi",
    }
    assert parts_to_wire(ContentPart(type="image", image_url="data:image/png;base64,AAA")) == {
        "type": "image_url",
        "image_url": {"url": "data:image/png;base64,AAA"},
    }


def test_messages_to_wire_multimodal() -> None:
    messages = [
        ChatMessage(
            role="user",
            content=[
                ContentPart(type="text", text="look"),
                ContentPart(type="image", image_url="http://img/x.png"),
            ],
        )
    ]
    wire = messages_to_wire(messages)
    assert wire[0]["role"] == "user"
    assert wire[0]["content"][0] == {"type": "text", "text": "look"}
    assert wire[0]["content"][1]["type"] == "image_url"


def test_parse_chat_response() -> None:
    data = {
        "model": "gpt-4o-mini",
        "choices": [{"message": {"role": "assistant", "content": "Hello world"}}],
        "usage": {"prompt_tokens": 7, "completion_tokens": 2},
    }
    response = parse_chat_response(data, "fallback")
    assert response.message.content == "Hello world"
    assert response.usage.prompt_tokens == 7
    assert response.usage.completion_tokens == 2


async def test_request_chat_sends_payload() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert body["model"] == "gpt-4o-mini"
        assert body["stream"] is False
        assert body["messages"][0]["role"] == "user"
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 1},
            },
        )

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    response = await request_chat(
        transport,
        ChatRequest(
            model="gpt-4o-mini",
            messages=[ChatMessage(role="user", content="hello")],
        ),
    )
    assert response.message.content == "hi"


async def test_request_chat_stream_collects_deltas() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        body = (
            'data: {"model":"m","choices":[{"delta":{"content":"Hel"}}]}\n\n'
            'data: {"model":"m","choices":[{"delta":{"content":"lo"}}]}\n\n'
            'data: {"model":"m","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=body)

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    chunks = [
        chunk
        async for chunk in request_chat_stream(
            transport,
            ChatRequest(model="m", messages=[ChatMessage(role="user", content="hey")]),
        )
    ]
    assert [c.delta for c in chunks] == ["Hel", "lo", ""]
    assert chunks[-1].finish_reason == "stop"


async def test_request_embeddings() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/embeddings"
        return httpx.Response(
            200,
            json={
                "model": "nomic-embed-text",
                "data": [
                    {"embedding": [0.1, 0.2]},
                    {"embedding": [0.3, 0.4]},
                ],
                "usage": {"prompt_tokens": 5, "completion_tokens": 0},
            },
        )

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    response = await request_embeddings(
        transport,
        EmbeddingRequest(model="nomic-embed-text", inputs=["a", "b"]),
    )
    assert len(response.embeddings) == 2
    assert response.embeddings[0].embedding == [0.1, 0.2]


async def test_request_models() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"id": "m1"}, {"id": "m2"}]},
        )

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    models = await request_models(transport)
    assert [m.id for m in models] == ["m1", "m2"]
