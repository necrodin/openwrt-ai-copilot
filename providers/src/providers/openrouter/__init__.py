"""OpenRouter provider adapter.

OpenRouter aggregates hundreds of models behind one OpenAI-compatible API. No
OpenRouter SDK is used; ``base_url`` defaults to ``https://openrouter.ai/api/v1``.
Optional route/attribution headers can be supplied via ``extra_headers`` in the
provider configuration.
"""

from providers.compat_provider import OpenAICompatibleProvider


class OpenRouterProvider(OpenAICompatibleProvider):
    provider_type = "openrouter"
    capability_defaults: set[str] = frozenset({"chat", "stream", "tools"})


__all__ = ["OpenRouterProvider"]
