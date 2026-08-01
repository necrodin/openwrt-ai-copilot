"""Shared OpenAI-compatible provider implementation.

Used by OpenAI, OpenRouter, vLLM, LM Studio and NVIDIA NIM. Each concrete
adapter only overrides ``provider_type`` (and, for NIM, adds ``rerank()``).

Request/response conversion lives in :mod:`providers.openai_compat`.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from ai.core.models import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    TokenUsage,
    Usage,
)
from ai.core.protocols import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDINGS,
    CAPABILITY_STREAM,
)
from providers.base import BaseProvider
from providers.openai_compat import (
    request_chat,
    request_chat_stream,
    request_embeddings,
    request_models,
)


def estimate_tokens(text: str) -> int:
    """Rough token estimate (chars / 4) used when a stream omits usage data."""
    return max(1, len(text) // 4)


class OpenAICompatibleProvider(BaseProvider):
    """Implements chat/stream/embeddings over an OpenAI-compatible endpoint."""

    provider_type: str = "compat"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})

    def _resolve_model(self, requested: str, default: str) -> str:
        return requested or default

    async def list_models(self) -> list[ModelInfo]:
        return await request_models(self._transport)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        resolved = self._resolve_model(request.model, self._config.model)
        response = await request_chat(
            self._transport,
            request.model_copy(update={"model": resolved}),
        )
        self._record(CAPABILITY_CHAT, response.usage)
        self._usage.cost_usd += self._cost(response.usage)
        return response

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        return self._stream(request)

    async def _stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        resolved = self._resolve_model(request.model, self._config.model)
        prompt_estimate = estimate_tokens(
            "".join(m.content if isinstance(m.content, str) else "" for m in request.messages)
        )
        completion_chars = 0
        error: Exception | None = None
        try:
            async for chunk in request_chat_stream(
                self._transport,
                request.model_copy(update={"model": resolved}),
            ):
                completion_chars += len(chunk.delta)
                yield chunk
        except Exception as exc:  # noqa: BLE001 - record and re-raise
            error = exc
            raise
        finally:
            usage = Usage(
                prompt_tokens=prompt_estimate,
                completion_tokens=estimate_tokens(str(completion_chars)),
            )
            self._record(CAPABILITY_STREAM, usage)
            self._usage.cost_usd += self._cost(usage)
            if error is not None:
                self._record_error()

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        resolved = self._resolve_model(
            request.model, self._config.embed_model or self._config.model
        )
        response = await request_embeddings(
            self._transport,
            request.model_copy(update={"model": resolved}),
        )
        self._record(CAPABILITY_EMBEDDINGS, response.usage)
        self._usage.cost_usd += self._cost(response.usage)
        return response

    def token_usage(self) -> TokenUsage:
        return super().token_usage()


__all__ = ["OpenAICompatibleProvider", "estimate_tokens"]
