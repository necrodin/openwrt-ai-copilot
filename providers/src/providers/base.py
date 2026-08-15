"""Shared provider base.

``BaseProvider`` implements the common contract: configuration-driven
instantiation, ``health()``, capability detection (``capabilities()``), token
accounting (``token_usage()``), and the shared multimodal ``vision()`` path.

Concrete adapters subclass ``BaseProvider`` and override the capability methods
they genuinely support. Methods for unsupported capabilities are inherited and
raise ``UnsupportedCapabilityError``; ``capabilities()`` reports them as
absent, so callers detect support instead of guessing.

The application never depends on any provider SDK — adapters only ever call
standard HTTP endpoints through :class:`ProviderTransport`.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Callable
from datetime import UTC, datetime

from ai.core.errors import ProviderError, UnsupportedCapabilityError
from ai.core.models import (
    ChatChunk,
    ChatMessage,
    ChatRequest,
    ChatResponse,
    ContentPart,
    EmbeddingRequest,
    EmbeddingResponse,
    ModelInfo,
    ProviderCapabilities,
    RerankRequest,
    RerankResponse,
    TokenUsage,
    Usage,
    VisionRequest,
    VisionResponse,
)
from ai.core.protocols import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDINGS,
    CAPABILITY_RERANK,
    CAPABILITY_STREAM,
    CAPABILITY_VISION,
    ChatProvider,
    EmbeddingProvider,
    RerankerProvider,
    VisionProvider,
)
from providers.capabilities import detect_capabilities
from providers.config import ProviderConfig
from providers.transport import ProviderTransport


def resolve_api_key(config: ProviderConfig) -> str | None:
    """Resolve the API key for a provider configuration.

    Resolution order:

    1. ``config.api_key`` — a key carried in-memory only (a draft probe's
       unsaved credential, or a key injected from the backend's encrypted
       credential store). Never serialized.
    2. a registered credential resolver (set by the backend via
       :func:`configure_api_key_resolver` to consult its encrypted store).
    3. the legacy environment-variable reference (``api_key_env`` /
       ``api_key_ref``) — retained so existing deployments keep working.

    The key value never lives in the config file; only the environment variable
    name (``api_key_env``) or a vault/environment reference (``api_key_ref``)
    is stored, and secure credentials are stored encrypted server-side.
    """
    if config.api_key:
        return config.api_key
    if _API_KEY_RESOLVER is not None:
        stored = _API_KEY_RESOLVER(config)
        if stored:
            return stored
    if config.api_key_env:
        return os.getenv(config.api_key_env)
    if config.api_key_ref:
        return os.getenv(config.api_key_ref)
    return None


#: Optional secure-store resolver installed by the application. A provider
#: configuration is turned into a live provider only after this returns the
#: encrypted-store credential for the provider type, so the key is decrypted
#: server-side and never persisted or transmitted as plaintext.
_API_KEY_RESOLVER: Callable[[ProviderConfig], str | None] | None = None


def configure_api_key_resolver(resolver: Callable[[ProviderConfig], str | None] | None) -> None:
    """Register (or clear) the secure credential resolver used by providers.

    The resolver receives a provider configuration and returns the API key from
    the application's encrypted credential store, or ``None`` when none is
    stored. Called once by the backend at startup.
    """
    global _API_KEY_RESOLVER
    _API_KEY_RESOLVER = resolver


class BaseProvider(ChatProvider, EmbeddingProvider, VisionProvider, RerankerProvider):
    """Shared implementation for every provider adapter."""

    provider_type: str = "base"
    #: Capabilities this provider type always supports, refined at runtime by
    #: capability detection.
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})

    def __init__(
        self,
        config: ProviderConfig,
        *,
        transport: ProviderTransport | None = None,
    ) -> None:
        self._config = config
        self.name = config.effective_name()
        self._transport = transport or ProviderTransport(
            base_url=config.effective_base_url(),
            api_key=resolve_api_key(config),
            extra_headers=config.extra_headers or None,
            timeout_seconds=config.timeout_seconds,
            verify_tls=config.verify_tls,
        )
        self._usage = TokenUsage()
        self._capabilities: ProviderCapabilities | None = None

    # ------------------------------------------------------------------ #
    # Provider contract                                                  #
    # ------------------------------------------------------------------ #

    @property
    def config(self) -> ProviderConfig:
        return self._config

    async def health(self) -> bool:
        try:
            await self.list_models()
            return True
        except ProviderError:
            return False

    async def capabilities(self) -> ProviderCapabilities:
        if self._capabilities is None:
            self._capabilities = await self._detect_capabilities()
        return self._capabilities

    def token_usage(self) -> TokenUsage:
        return self._usage.model_copy(deep=True)

    def static_capabilities(self) -> set[str]:
        """Declared capabilities without probing the network.

        Used for synchronous routing decisions (e.g. picking a provider for a
        capability in :class:`ProviderManager`). An explicit ``capabilities``
        override in the config takes precedence.
        """
        if self._config.capabilities is not None:
            return set(self._config.capabilities)
        return set(self.capability_defaults)

    # ------------------------------------------------------------------ #
    # Capability method defaults (raise for unsupported capabilities)    #
    # ------------------------------------------------------------------ #

    async def chat(self, request: ChatRequest) -> ChatResponse:
        raise self._unsupported(CAPABILITY_CHAT)

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatChunk]:
        raise self._unsupported(CAPABILITY_STREAM)

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        raise self._unsupported(CAPABILITY_EMBEDDINGS)

    async def vision(self, request: VisionRequest) -> VisionResponse:
        if not (await self.supports(CAPABILITY_VISION)):
            raise self._unsupported(CAPABILITY_VISION)
        response = await self.chat(_vision_to_chat(request))
        content = response.message.content
        text = content if isinstance(content, str) else ""
        return VisionResponse(model=response.model, text=text, usage=response.usage)

    async def rerank(self, request: RerankRequest) -> RerankResponse:
        raise self._unsupported(CAPABILITY_RERANK)

    def dimensions(self) -> int | None:
        return self._config.embed_dimensions

    async def list_models(self) -> list[ModelInfo]:
        raise UnsupportedCapabilityError(f"Provider {self.name!r} cannot list models")

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _unsupported(self, capability: str) -> UnsupportedCapabilityError:
        return UnsupportedCapabilityError(
            f"Provider {self.name!r} ({self.provider_type}) does not support "
            f"capability {capability!r}. Check capabilities()."
        )

    async def _detect_capabilities(self) -> ProviderCapabilities:
        catalog: list[str] = []
        try:
            models = await self.list_models()
            catalog = [model.id for model in models]
        except (ProviderError, UnsupportedCapabilityError):
            catalog = []

        cfg = self._config
        configured = [
            m for m in (cfg.model, cfg.embed_model, cfg.vision_model, cfg.rerank_model) if m
        ]
        forced = cfg.capabilities
        detected = detect_capabilities(
            declared=set(self.capability_defaults),
            configured_models=configured,
            catalog_models=catalog,
            forced=forced,
        )
        detected.detected_at = datetime.now(UTC)
        return detected

    def _record(self, capability: str, usage: Usage) -> None:
        self._usage.merge(capability, usage)

    def _record_error(self) -> None:
        self._usage.add_error()

    def _cost(self, usage: Usage) -> float:
        cfg = self._config
        return (
            usage.prompt_tokens / 1000 * cfg.cost_per_1k_prompt
            + usage.completion_tokens / 1000 * cfg.cost_per_1k_completion
        )

    async def aclose(self) -> None:
        await self._transport.aclose()

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} type={self.provider_type!r}>"


def _vision_to_chat(request: VisionRequest) -> ChatRequest:
    parts: list[ContentPart] = [ContentPart(type="text", text=request.prompt)]
    parts.extend(request.images)
    return ChatRequest(
        model=request.model,
        messages=[ChatMessage(role="user", content=parts)],
        max_tokens=request.max_tokens,
    )


__all__ = [
    "BaseProvider",
    "ProviderTransport",
    "configure_api_key_resolver",
    "resolve_api_key",
]
