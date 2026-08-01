"""Unified, provider-agnostic data model.

All provider adapters translate to/from these types. Downstream code (backend,
rag, vision) only ever sees these shapes — never provider-specific payloads.

An empty ``model`` field on a request means "use the provider's configured
default model", which is what makes providers swappable via configuration
without changing caller code.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant", "tool"]
PartType = Literal["text", "image"]


class Usage(BaseModel):
    """Per-call token usage as reported by a provider."""

    prompt_tokens: int = 0
    completion_tokens: int = 0


class TokenUsage(BaseModel):
    """Cumulative token accounting for a provider instance.

    Exposed through ``Provider.token_usage()``. Every call increments the
    counters so operators can meter and cost provider usage.
    """

    prompt_tokens: int = 0
    completion_tokens: int = 0
    calls: int = 0
    errors: int = 0
    cost_usd: float = 0.0
    by_capability: dict[str, Usage] = Field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def merge(self, capability: str, usage: Usage) -> None:
        self.prompt_tokens += usage.prompt_tokens
        self.completion_tokens += usage.completion_tokens
        self.calls += 1
        bucket = self.by_capability.setdefault(capability, Usage())
        bucket.prompt_tokens += usage.prompt_tokens
        bucket.completion_tokens += usage.completion_tokens

    def add_error(self) -> None:
        self.errors += 1


class ProviderCapabilities(BaseModel):
    """What a provider actually supports, discovered by capability detection.

    ``static`` is True when the result comes purely from the provider's declared
    defaults / configuration; False when a runtime probe contributed to it.
    """

    chat: bool = False
    stream: bool = False
    embeddings: bool = False
    vision: bool = False
    rerank: bool = False
    tools: bool = False
    models: list[str] = Field(default_factory=list)
    detected_at: datetime | None = None
    static: bool = True

    @property
    def as_set(self) -> set[str]:
        result: set[str] = set()
        if self.chat:
            result.add("chat")
        if self.stream:
            result.add("stream")
        if self.embeddings:
            result.add("embeddings")
        if self.vision:
            result.add("vision")
        if self.rerank:
            result.add("rerank")
        if self.tools:
            result.add("tools")
        return result


class ContentPart(BaseModel):
    """A single multimodal content block inside a chat message."""

    type: PartType
    text: str | None = None
    # For image parts: a data URI ("data:image/png;base64,...") or hosted URL.
    image_url: str | None = None


class ChatMessage(BaseModel):
    role: Role
    content: str | list[ContentPart] = ""
    name: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[dict] | None = None


class ChatRequest(BaseModel):
    model: str = ""
    messages: list[ChatMessage]
    temperature: float | None = None
    max_tokens: int | None = None
    stream: bool = False
    tools: list[dict] | None = None


class ChatResponse(BaseModel):
    model: str
    message: ChatMessage
    usage: Usage = Field(default_factory=Usage)


class ChatChunk(BaseModel):
    model: str
    delta: str
    finish_reason: str | None = None


class ModelInfo(BaseModel):
    id: str
    capabilities: set[str] = Field(default_factory=set)
    context_window: int | None = None


class EmbeddingRequest(BaseModel):
    model: str = ""
    inputs: list[str]
    dimensions: int | None = None


class EmbeddingVector(BaseModel):
    embedding: list[float]


class EmbeddingResponse(BaseModel):
    model: str
    embeddings: list[EmbeddingVector]
    usage: Usage = Field(default_factory=Usage)


class VisionRequest(BaseModel):
    model: str = ""
    prompt: str
    images: list[ContentPart] = Field(default_factory=list)
    max_tokens: int | None = None


class VisionResponse(BaseModel):
    model: str
    text: str
    usage: Usage = Field(default_factory=Usage)


class RerankRequest(BaseModel):
    model: str = ""
    query: str
    documents: list[str]
    top_n: int | None = None


class RerankResult(BaseModel):
    index: int
    document: str
    score: float


class RerankResponse(BaseModel):
    model: str
    results: list[RerankResult]
    usage: Usage = Field(default_factory=Usage)


__all__ = [
    "ChatChunk",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ContentPart",
    "EmbeddingRequest",
    "EmbeddingResponse",
    "EmbeddingVector",
    "ModelInfo",
    "ProviderCapabilities",
    "RerankRequest",
    "RerankResponse",
    "RerankResult",
    "TokenUsage",
    "Usage",
    "VisionRequest",
    "VisionResponse",
]
