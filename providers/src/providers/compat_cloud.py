"""Thin OpenAI-compatible adapters for common cloud/self-hosted backends.

Each of these services exposes an OpenAI-compatible ``/chat/completions``
(and, where supported, ``/embeddings``/``/models``) endpoint — either natively
(OpenRouter, Together, Groq, DeepSeek, Mistral, xAI, Cohere, Perplexity, vLLM,
LM Studio, NVIDIA NIM) or via an official OpenAI-compatible gateway (Azure
OpenAI, Anthropic, Google Gemini). They all reuse the shared
:class:`OpenAICompatibleProvider` implementation; the class here only pins the
``provider_type`` key and its default endpoint (defined in ``config.py``).

No vendor SDK is used and no bespoke wire protocol is invented: this is the
same existing OpenAI-compatible adapter with different defaults, so a provider
"works" exactly when the endpoint is genuinely OpenAI-compatible — the
connection test verifies that rather than assuming it.
"""

from __future__ import annotations

from ai.core.protocols import CAPABILITY_CHAT, CAPABILITY_STREAM
from providers.compat_provider import OpenAICompatibleProvider


class CompatProvider(OpenAICompatibleProvider):
    """Generic "Custom / OpenAI-compatible" backend (requires a base URL)."""

    provider_type = "compat"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class AzureOpenAIProvider(OpenAICompatibleProvider):
    provider_type = "azure_openai"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class AnthropicProvider(OpenAICompatibleProvider):
    provider_type = "anthropic"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class GeminiProvider(OpenAICompatibleProvider):
    provider_type = "gemini"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class TogetherProvider(OpenAICompatibleProvider):
    provider_type = "together"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class GroqProvider(OpenAICompatibleProvider):
    provider_type = "groq"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class DeepSeekProvider(OpenAICompatibleProvider):
    provider_type = "deepseek"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class MistralProvider(OpenAICompatibleProvider):
    provider_type = "mistral"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class XAIProvider(OpenAICompatibleProvider):
    provider_type = "xai"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class CohereProvider(OpenAICompatibleProvider):
    provider_type = "cohere"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class PerplexityProvider(OpenAICompatibleProvider):
    provider_type = "perplexity"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class FireworksProvider(OpenAICompatibleProvider):
    provider_type = "fireworks"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


class CerebrasProvider(OpenAICompatibleProvider):
    provider_type = "cerebras"
    capability_defaults: set[str] = frozenset({CAPABILITY_CHAT, CAPABILITY_STREAM})


__all__ = [
    "AnthropicProvider",
    "AzureOpenAIProvider",
    "CerebrasProvider",
    "CohereProvider",
    "CompatProvider",
    "DeepSeekProvider",
    "FireworksProvider",
    "GeminiProvider",
    "GroqProvider",
    "MistralProvider",
    "PerplexityProvider",
    "TogetherProvider",
    "XAIProvider",
]
