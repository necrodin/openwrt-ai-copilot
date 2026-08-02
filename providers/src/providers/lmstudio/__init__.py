"""LM Studio provider adapter.

LM Studio runs a local OpenAI-compatible server (default
``http://localhost:1234/v1``). No LM Studio SDK is used. Embedding support is
detected at runtime when an embedding model is loaded.
"""

from providers.compat_provider import OpenAICompatibleProvider


class LMStudioProvider(OpenAICompatibleProvider):
    provider_type = "lmstudio"
    capability_defaults: set[str] = frozenset({"chat", "stream", "embeddings", "tools"})


__all__ = ["LMStudioProvider"]
