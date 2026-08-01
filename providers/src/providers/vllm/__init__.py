"""vLLM provider adapter.

vLLM serves models via an OpenAI-compatible server (default
``http://localhost:8000/v1``) with chat, streaming, embeddings, and — for
supported models — vision. No vLLM SDK is used.
"""

from providers.compat_provider import OpenAICompatibleProvider


class VLLMProvider(OpenAICompatibleProvider):
    provider_type = "vllm"
    capability_defaults: set[str] = frozenset({"chat", "stream", "tools"})


__all__ = ["VLLMProvider"]
