"""Ollama provider adapter (native API).

Uses Ollama's native endpoints (``/api/tags``, ``/api/chat``, ``/api/embed``) —
no Ollama SDK. Chat, streaming (NDJSON), embeddings, and vision (multimodal
chat) are supported. Reranking is not offered by Ollama; capability detection
reports it absent and ``rerank()`` raises ``UnsupportedCapabilityError``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ai.core.models import (
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    EmbeddingVector,
    ModelInfo,
    Usage,
)
from ai.core.protocols import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDINGS,
    CAPABILITY_STREAM,
)
from providers.base import BaseProvider


def _to_base64(image_url: str) -> str:
    """Strip a data-URI prefix (``data:image/png;base64,``) leaving raw base64."""
    if image_url.startswith("data:"):
        return image_url.split(",", 1)[1]
    return image_url


def _messages_to_ollama(messages: list[ChatMessage]) -> list[dict]:
    out: list[dict] = []
    for message in messages:
        item: dict = {"role": message.role}
        if isinstance(message.content, list):
            text = " ".join(part.text or "" for part in message.content if part.type == "text")
            images = [
                _to_base64(part.image_url)
                for part in message.content
                if part.type == "image" and part.image_url
            ]
            item["content"] = text
            if images:
                item["images"] = images
        else:
            item["content"] = message.content
        if message.tool_calls:
            item["tool_calls"] = message.tool_calls
        out.append(item)
    return out


def _parse_usage(data: dict) -> Usage:
    return Usage(
        prompt_tokens=int(data.get("prompt_eval_count") or 0),
        completion_tokens=int(data.get("eval_count") or 0),
    )


class OllamaProvider(BaseProvider):
    provider_type = "ollama"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})

    def _payload(self, request: ChatRequest, *, stream: bool) -> dict:
        payload: dict = {
            "model": request.model or self._config.model,
            "messages": _messages_to_ollama(request.messages),
            "stream": stream,
        }
        options: dict = {}
        if request.temperature is not None:
            options["temperature"] = request.temperature
        if request.max_tokens is not None:
            options["num_predict"] = request.max_tokens
        if options:
            payload["options"] = options
        if request.tools:
            payload["tools"] = request.tools
        return payload

    async def list_models(self) -> list[ModelInfo]:
        data = await self._transport.get("/api/tags")
        models: list[ModelInfo] = []
        for entry in data.get("models", []):
            raw_caps = set(entry.get("capabilities", []))
            caps = set()
            if "completion" in raw_caps:
                caps.add(CAPABILITY_CHAT)
            if "embedding" in raw_caps:
                caps.add(CAPABILITY_EMBEDDINGS)
            if "vision" in raw_caps:
                caps.add("vision")
            models.append(ModelInfo(id=entry["name"], capabilities=caps))
        return models

    async def chat(self, request: ChatRequest) -> ChatResponse:
        data = await self._transport.post_json("/api/chat", self._payload(request, stream=False))
        message = data.get("message") or {}
        response = ChatResponse(
            model=data.get("model") or request.model or self._config.model,
            message=ChatMessage(
                role=message.get("role") or "assistant",
                content=message.get("content") or "",
            ),
            usage=_parse_usage(data),
        )
        self._record(CAPABILITY_CHAT, response.usage)
        self._usage.cost_usd += self._cost(response.usage)
        return response

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        return self._stream(request)

    async def _stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        error: Exception | None = None
        completion_chars = 0
        prompt_tokens = 0
        try:
            async for data in self._transport.post_ndjson(
                "/api/chat", self._payload(request, stream=True)
            ):
                message = data.get("message") or {}
                content = message.get("content") or ""
                if content:
                    completion_chars += len(content)
                    yield ChatChunk(
                        model=data.get("model") or request.model or self._config.model,
                        delta=content,
                        finish_reason=data.get("done_reason"),
                    )
                elif data.get("done"):
                    yield ChatChunk(
                        model=data.get("model") or request.model or self._config.model,
                        delta="",
                        finish_reason=data.get("done_reason"),
                    )
                    prompt_tokens = int(data.get("prompt_eval_count") or 0)
        except Exception as exc:  # noqa: BLE001
            error = exc
            raise
        finally:
            usage = Usage(
                prompt_tokens=prompt_tokens,
                completion_tokens=max(1, completion_chars // 4),
            )
            self._record(CAPABILITY_STREAM, usage)
            self._usage.cost_usd += self._cost(usage)
            if error is not None:
                self._record_error()

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        model = request.model or self._config.embed_model or self._config.model
        payload: dict = {"model": model, "input": request.inputs}
        data = await self._transport.post_json("/api/embed", payload)
        vectors = [EmbeddingVector(embedding=vec) for vec in data.get("embeddings", [])]
        usage = Usage(prompt_tokens=int(data.get("prompt_eval_count") or 0))
        response = EmbeddingResponse(
            model=data.get("model") or model,
            embeddings=vectors,
            usage=usage,
        )
        self._record(CAPABILITY_EMBEDDINGS, usage)
        self._usage.cost_usd += self._cost(usage)
        return response


__all__ = ["OllamaProvider"]
