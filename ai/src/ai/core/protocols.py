"""Provider interfaces — the contract every AI provider adapter satisfies.

The four capability interfaces are:

- ``ChatProvider``      — ``chat()``, ``stream()``, ``list_models()``
- ``EmbeddingProvider`` — ``embeddings()``, ``dimensions()``
- ``VisionProvider``    — ``vision()`` (multimodal chat)
- ``RerankerProvider``  — ``rerank()``

Every concrete provider implements **all four** interfaces plus the common
``Provider`` contract (``health()``, ``capabilities()`` capability detection,
``token_usage()``). A provider reports which capabilities it genuinely supports
through ``capabilities()``; calling a capability it does not support raises
``UnsupportedCapabilityError``.

This module imports nothing but the ``ai.core`` data model — no provider SDK,
ever.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from ai.core.models import (
    ChatChunk,
    ChatRequest,
    ChatResponse,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    ProviderCapabilities,
    RerankRequest,
    RerankResponse,
    TokenUsage,
    VisionRequest,
    VisionResponse,
)

CAPABILITY_CHAT = "chat"
CAPABILITY_STREAM = "stream"
CAPABILITY_EMBEDDINGS = "embeddings"
CAPABILITY_VISION = "vision"
CAPABILITY_RERANK = "rerank"
CAPABILITY_TOOLS = "tools"

ALL_CAPABILITIES = frozenset(
    {
        CAPABILITY_CHAT,
        CAPABILITY_STREAM,
        CAPABILITY_EMBEDDINGS,
        CAPABILITY_VISION,
        CAPABILITY_RERANK,
        CAPABILITY_TOOLS,
    }
)


class Provider(ABC):
    """Common contract implemented by every provider adapter."""

    provider_type: str
    name: str

    @abstractmethod
    async def health(self) -> bool:
        """Return True when the provider endpoint is reachable and healthy."""

    @abstractmethod
    async def capabilities(self) -> ProviderCapabilities:
        """Return the capabilities this provider actually supports.

        Capability detection is both static (declared defaults + config) and
        dynamic (a runtime probe of the endpoint's model catalog).
        """

    @abstractmethod
    def token_usage(self) -> TokenUsage:
        """Return a snapshot of cumulative token usage and cost."""

    async def supports(self, capability: str) -> bool:
        """Return True if the provider reports support for ``capability``."""
        return capability in (await self.capabilities()).as_set


class ChatProvider(Provider):
    """Chat / completion capability."""

    @abstractmethod
    async def chat(self, request: ChatRequest) -> ChatResponse:
        """Complete a chat conversation and return the full response."""

    @abstractmethod
    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        """Complete a chat conversation, yielding deltas as they arrive."""

    @abstractmethod
    async def list_models(self) -> list[ModelInfo]:
        """List the models the provider endpoint exposes."""


class EmbeddingProvider(Provider):
    """Embedding capability."""

    @abstractmethod
    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        """Embed a batch of texts."""

    @abstractmethod
    def dimensions(self) -> int | None:
        """Return the embedding dimensions, when known statically."""


class VisionProvider(Provider):
    """Vision (multimodal image understanding) capability.

    Implemented as multimodal chat: the request carries text + image content
    parts that are routed through the same chat path.
    """

    @abstractmethod
    async def vision(self, request: VisionRequest) -> VisionResponse:
        """Describe or answer a question about the supplied images."""


class RerankerProvider(Provider):
    """Reranking capability (used by the RAG pipeline)."""

    @abstractmethod
    async def rerank(self, request: RerankRequest) -> RerankResponse:
        """Score ``documents`` against ``query`` and return top-N results."""


__all__ = [
    "ALL_CAPABILITIES",
    "CAPABILITY_CHAT",
    "CAPABILITY_EMBEDDINGS",
    "CAPABILITY_RERANK",
    "CAPABILITY_STREAM",
    "CAPABILITY_TOOLS",
    "CAPABILITY_VISION",
    "ChatProvider",
    "EmbeddingProvider",
    "Provider",
    "RerankerProvider",
    "VisionProvider",
]
