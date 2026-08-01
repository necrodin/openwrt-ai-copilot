"""Capability detection heuristics.

Providers are probed at runtime (their model catalog is fetched) and the model
names — plus the provider's static defaults and configuration — are combined to
decide which capabilities the provider genuinely supports. This is the
"future capability detection" of the abstraction: a provider that starts
serving vision or embedding models is picked up automatically without code
changes.

Model-name matching is heuristic; an explicit ``capabilities`` override in the
provider configuration always wins.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ai.core.models import ProviderCapabilities
from ai.core.protocols import (
    CAPABILITY_CHAT,
    CAPABILITY_EMBEDDINGS,
    CAPABILITY_RERANK,
    CAPABILITY_STREAM,
    CAPABILITY_TOOLS,
    CAPABILITY_VISION,
)

_EMBEDDING_MARKERS = (
    "embed",
    "bge",
    "e5-",
    "nomic-embed",
    "text-embedding",
    "gte-",
    "gte_",
    "arctic-embed",
    "jina-embed",
)

_VISION_MARKERS = (
    "vision",
    "llava",
    "qwen2-vl",
    "qwen3-vl",
    "qwen-vl",
    "vl-",
    "-vl",
    "gemini",
    "gpt-4o",
    "gpt-4.1",
    "claude-3",
    "claude-3.5",
    "pixtral",
    "moondream",
    "cogvlm",
    "llama3.2-vision",
    "llama-3.2-11b-vision",
    "deepseek-vl",
    "internvl",
    "omni",
    "multimodal",
    "molmo",
    "phi-3.5-vision",
    "glm-4v",
    "idefics",
    "fuyu",
    "paligemma",
)

_RERANK_MARKERS = ("rerank", "reranker", "cross-encoder", "cross_encoder")


def has_embedding_model(model_name: str) -> bool:
    name = model_name.lower()
    return any(marker in name for marker in _EMBEDDING_MARKERS)


def has_vision_model(model_name: str) -> bool:
    name = model_name.lower()
    return any(marker in name for marker in _VISION_MARKERS)


def has_rerank_model(model_name: str) -> bool:
    name = model_name.lower()
    return any(marker in name for marker in _RERANK_MARKERS)


def detect_capabilities(
    *,
    declared: set[str],
    configured_models: list[str],
    catalog_models: list[str],
    forced: set[str] | None = None,
) -> ProviderCapabilities:
    """Combine static defaults, configured models, and a runtime model catalog.

    Args:
        declared: capability identifiers the provider type always supports
            (e.g. ``{"chat", "stream"}``).
        configured_models: models named in the provider configuration
            (``model``, ``embed_model``, ``vision_model``, ``rerank_model``).
        catalog_models: model IDs discovered by probing the endpoint.
        forced: explicit configuration override; when provided it wins and the
            result is reported as fully static.
    """
    if forced is not None:
        caps = set(forced) & {
            CAPABILITY_CHAT,
            CAPABILITY_STREAM,
            CAPABILITY_EMBEDDINGS,
            CAPABILITY_VISION,
            CAPABILITY_RERANK,
            CAPABILITY_TOOLS,
        }
        return ProviderCapabilities(
            chat=CAPABILITY_CHAT in caps,
            stream=CAPABILITY_STREAM in caps,
            embeddings=CAPABILITY_EMBEDDINGS in caps,
            vision=CAPABILITY_VISION in caps,
            rerank=CAPABILITY_RERANK in caps,
            tools=CAPABILITY_TOOLS in caps,
            models=list(configured_models + catalog_models),
            detected_at=datetime.now(UTC),
            static=True,
        )

    chat = CAPABILITY_CHAT in declared
    stream = CAPABILITY_STREAM in declared
    tools = CAPABILITY_TOOLS in declared
    embeddings = CAPABILITY_EMBEDDINGS in declared
    vision = CAPABILITY_VISION in declared
    rerank = CAPABILITY_RERANK in declared

    names = [m.lower() for m in configured_models + catalog_models]
    if any(has_embedding_model(name) for name in names):
        embeddings = True
    if any(has_vision_model(name) for name in names):
        vision = True
    if any(has_rerank_model(name) for name in names):
        rerank = True

    return ProviderCapabilities(
        chat=chat,
        stream=stream,
        embeddings=embeddings,
        vision=vision,
        rerank=rerank,
        tools=tools,
        models=list(configured_models + catalog_models),
        detected_at=datetime.now(UTC),
        static=not catalog_models,
    )


__all__ = [
    "detect_capabilities",
    "has_embedding_model",
    "has_rerank_model",
    "has_vision_model",
]
