"""NVIDIA NV-Embed embedding provider.

First-class embedding adapter for NVIDIA's NV-Embed model family, served by a
NIM endpoint through the OpenAI-compatible ``/embeddings`` API. On top of the
shared OpenAI-compatible implementation it adds NV-Embed semantics:

- ``input_type`` (``query`` | ``passage``) for retrieval-aware instructions,
- optional L2 normalization of the returned vectors,
- the same token-usage accounting as every other adapter.

No NVIDIA SDK is used; all I/O goes through ``ProviderTransport`` over plain
HTTP, exactly like the other providers.
"""

from __future__ import annotations

from ai.core.models import EmbeddingRequest, EmbeddingResponse
from ai.core.protocols import CAPABILITY_EMBEDDINGS
from providers.compat_provider import OpenAICompatibleProvider
from providers.openai_compat import request_embeddings

#: Fallback model used when neither the request nor the config names one.
DEFAULT_NV_EMBED_MODEL = "nvidia/NV-Embed-QA-Mistral-4B"


class NVEmbedProvider(OpenAICompatibleProvider):
    """Embeddings-only adapter for NVIDIA NV-Embed models via NIM."""

    provider_type = "nvembed"
    capability_defaults: set[str] = frozenset({CAPABILITY_EMBEDDINGS})

    def _resolve_embed_model(self, requested: str) -> str:
        return requested or self._config.embed_model or self._config.model or DEFAULT_NV_EMBED_MODEL

    async def embeddings(self, request: EmbeddingRequest) -> EmbeddingResponse:
        resolved = self._resolve_embed_model(request.model)
        response = await request_embeddings(
            self._transport,
            request.model_copy(update={"model": resolved}),
            include_input_type=True,
        )
        self._record(CAPABILITY_EMBEDDINGS, response.usage)
        self._usage.cost_usd += self._cost(response.usage)
        return response


__all__ = ["DEFAULT_NV_EMBED_MODEL", "NVEmbedProvider"]
