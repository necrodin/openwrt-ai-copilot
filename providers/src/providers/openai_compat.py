"""Shared OpenAI-compatible protocol implementation.

OpenAI, OpenRouter, vLLM, LM Studio and NVIDIA NIM all expose OpenAI-compatible
HTTP endpoints for chat and embeddings. This module implements that wire
protocol once (request encoding + response decoding) so the adapters stay thin.

No vendor SDK is used — plain HTTP via :class:`ProviderTransport`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from ai.core.models import (
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ContentPart,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    ModelInfo,
    Usage,
)
from providers.transport import ProviderTransport


def parts_to_wire(part: ContentPart) -> dict[str, Any]:
    if part.type == "image":
        return {"type": "image_url", "image_url": {"url": part.image_url}}
    return {"type": "text", "text": part.text or ""}


def messages_to_wire(messages: list[ChatMessage]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for message in messages:
        item: dict[str, Any] = {"role": message.role}
        if isinstance(message.content, list):
            item["content"] = [parts_to_wire(part) for part in message.content]
        else:
            item["content"] = message.content
        if message.name:
            item["name"] = message.name
        if message.tool_call_id:
            item["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            item["tool_calls"] = message.tool_calls
        out.append(item)
    return out


def _chat_payload(request: ChatRequest, *, stream: bool) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": request.model,
        "messages": messages_to_wire(request.messages),
        "stream": stream,
    }
    if request.temperature is not None:
        payload["temperature"] = request.temperature
    if request.max_tokens is not None:
        payload["max_tokens"] = request.max_tokens
    if request.tools:
        payload["tools"] = request.tools
    return payload


def _parse_usage(data: dict[str, Any]) -> Usage:
    usage = data.get("usage") or {}
    return Usage(
        prompt_tokens=int(usage.get("prompt_tokens") or 0),
        completion_tokens=int(usage.get("completion_tokens") or 0),
    )


def parse_chat_response(data: dict[str, Any], fallback_model: str) -> ChatResponse:
    choice = (data.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    content = message.get("content")
    return ChatResponse(
        model=data.get("model") or fallback_model,
        message=ChatMessage(
            role=message.get("role") or "assistant",
            content=content or "",
            tool_calls=message.get("tool_calls"),
        ),
        usage=_parse_usage(data),
    )


async def request_chat(transport: ProviderTransport, request: ChatRequest) -> ChatResponse:
    data = await transport.post_json("/chat/completions", _chat_payload(request, stream=False))
    return parse_chat_response(data, request.model)


async def request_chat_stream(
    transport: ProviderTransport, request: ChatRequest
) -> AsyncIterator[ChatChunk]:
    async for data_payload in transport.post_sse(
        "/chat/completions", _chat_payload(request, stream=True)
    ):
        if data_payload == "[DONE]":
            break
        try:
            import json

            event = json.loads(data_payload)
        except ValueError:
            continue
        choice = (event.get("choices") or [{}])[0]
        delta = choice.get("delta") or {}
        content = delta.get("content")
        finish_reason = choice.get("finish_reason")
        if content:
            yield ChatChunk(
                model=event.get("model") or request.model,
                delta=content,
                finish_reason=finish_reason,
            )
        elif finish_reason:
            yield ChatChunk(
                model=event.get("model") or request.model,
                delta="",
                finish_reason=finish_reason,
            )


async def request_embeddings(
    transport: ProviderTransport, request: EmbeddingRequest
) -> EmbeddingResponse:
    payload: dict[str, Any] = {"model": request.model, "input": request.inputs}
    if request.dimensions is not None:
        payload["dimensions"] = request.dimensions
    data = await transport.post_json("/embeddings", payload)
    vectors = [
        EmbeddingVector(embedding=item["embedding"])
        for item in data.get("data", [])
        if item.get("embedding") is not None
    ]
    return EmbeddingResponse(
        model=data.get("model") or request.model,
        embeddings=vectors,
        usage=_parse_usage(data),
    )


async def request_models(transport: ProviderTransport) -> list[ModelInfo]:
    data = await transport.get("/models")
    return [ModelInfo(id=item["id"]) for item in data.get("data", [])]


__all__ = [
    "messages_to_wire",
    "parse_chat_response",
    "parts_to_wire",
    "request_chat",
    "request_chat_stream",
    "request_embeddings",
    "request_models",
]
