"""OpenAI provider adapter.

Cloud provider accessed through the OpenAI-compatible HTTP API. No OpenAI SDK
is used; ``base_url`` defaults to ``https://api.openai.com/v1`` and the API key
is referenced by environment variable in the provider configuration.
"""

from providers.compat_provider import OpenAICompatibleProvider


class OpenAIProvider(OpenAICompatibleProvider):
    provider_type = "openai"
    capability_defaults: set[str] = frozenset({"chat", "stream", "embeddings", "tools"})


__all__ = ["OpenAIProvider"]
