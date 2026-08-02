"""NVIDIA NIM provider adapter.

NIM exposes OpenAI-compatible chat/embeddings/vision plus a dedicated rerank
endpoint (``/v1/rerank``). The adapter builds on the shared OpenAI-compatible
implementation and adds ``rerank()``. No NVIDIA SDK is used.
"""

from __future__ import annotations

from ai.core.models import RerankRequest, RerankResponse, RerankResult, Usage
from ai.core.protocols import CAPABILITY_EMBEDDINGS, CAPABILITY_RERANK
from providers.compat_provider import OpenAICompatibleProvider


class NIMProvider(OpenAICompatibleProvider):
    provider_type = "nim"
    capability_defaults: set[str] = frozenset(
        {CAPABILITY_EMBEDDINGS, CAPABILITY_RERANK} | OpenAICompatibleProvider.capability_defaults
    )

    async def rerank(self, request: RerankRequest) -> RerankResponse:
        model = request.model or self._config.rerank_model or self._config.model
        payload: dict = {
            "model": model,
            "query": request.query,
            "documents": request.documents,
        }
        if request.top_n is not None:
            payload["top_n"] = request.top_n
        data = await self._transport.post_json("/rerank", payload)
        results = [
            RerankResult(
                index=int(item["index"]),
                document=self._doc_for(item, request.documents),
                score=float(item.get("relevance_score") or item.get("score") or 0.0),
            )
            for item in data.get("results", [])
        ]
        usage = Usage(
            prompt_tokens=int(data.get("prompt_tokens") or 0),
            completion_tokens=int(data.get("completion_tokens") or 0),
        )
        response = RerankResponse(
            model=data.get("model") or model,
            results=results,
            usage=usage,
        )
        self._record(CAPABILITY_RERANK, usage)
        self._usage.cost_usd += self._cost(usage)
        return response

    @staticmethod
    def _doc_for(item: dict, documents: list[str]) -> str:
        inline = item.get("document")
        if inline:
            return str(inline)
        index = int(item.get("index", -1))
        if 0 <= index < len(documents):
            return documents[index]
        return ""


__all__ = ["NIMProvider"]
