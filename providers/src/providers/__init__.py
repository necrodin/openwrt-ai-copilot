"""OpenWrt AI Copilot — pluggable AI provider adapters.

Supported providers: ollama, nim, openai, openrouter, lmstudio, vllm.

Each provider subpackage implements the ``ai.core`` ABC interfaces
(``ChatProvider``, ``EmbeddingProvider``, ``VisionProvider``,
``RerankerProvider``). The package is a thin layer: no provider SDK is
required; all adapters talk to standard HTTP endpoints (OpenAI-compatible where
possible, native Ollama where not).

Instances are created from configuration via :func:`providers.factory.create_provider`
or :func:`providers.factory.create_provider_manager` — switching providers never
touches application code.
"""

from __future__ import annotations

__version__ = "1.0.0"

from providers.base import BaseProvider, resolve_api_key
from providers.capabilities import (
    detect_capabilities,
    has_embedding_model,
    has_rerank_model,
    has_vision_model,
)
from providers.config import (
    DEFAULT_BASE_URLS,
    SUPPORTED_PROVIDER_TYPES,
    ProviderConfig,
    ProvidersConfig,
)
from providers.embedding import (
    RETRYABLE_EXCEPTIONS,
    EmbeddingError,
    EmbeddingFactory,
    NoEmbeddingProviderError,
    RetryPolicy,
    chunk_texts,
)
from providers.factory import (
    ProviderManager,
    available_provider_types,
    create_provider,
    create_provider_manager,
    register_provider,
    unregister_provider,
)
from providers.nv_embed import DEFAULT_NV_EMBED_MODEL, NVEmbedProvider
from providers.rerank import NoRerankProviderError, RerankError, RerankFactory
from providers.transport import ProviderTransport

__all__ = [
    "DEFAULT_BASE_URLS",
    "DEFAULT_NV_EMBED_MODEL",
    "SUPPORTED_PROVIDER_TYPES",
    "BaseProvider",
    "EmbeddingError",
    "EmbeddingFactory",
    "NVEmbedProvider",
    "NoEmbeddingProviderError",
    "NoRerankProviderError",
    "ProviderConfig",
    "RerankError",
    "RerankFactory",
    "ProviderManager",
    "ProviderTransport",
    "ProvidersConfig",
    "RETRYABLE_EXCEPTIONS",
    "RetryPolicy",
    "available_provider_types",
    "chunk_texts",
    "create_provider",
    "create_provider_manager",
    "detect_capabilities",
    "has_embedding_model",
    "has_rerank_model",
    "has_vision_model",
    "register_provider",
    "resolve_api_key",
    "unregister_provider",
]
