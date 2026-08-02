"""OpenWrt AI Copilot — RAG integration layer.

Sprint 9B bridges the provider-independent Retrieval Core (``rag``) to the AI
provider facade (``ai``/``providers``): :class:`~rag.ai.RAGEngine` turns a
retrieved, reranked context into a grounded, cited chat answer (streaming or
not), :class:`~rag.ai.RAGSession` owns a conversation, and the helper modules
provide configuration, an embedding cache, and the rerank bridge.

This subpackage is the only place ``rag`` depends on ``ai``/``providers``; the
core (``rag`` top level) stays provider-independent.
"""

from __future__ import annotations

from rag.ai.cache import CachedEmbedder, EmbeddingCache
from rag.ai.config import RAGConfiguration
from rag.ai.engine import RAGEngine, build_memory, build_retrieval_config
from rag.ai.errors import (
    NoChatProviderError,
    RAGConfigurationError,
    RAGError,
    RAGProviderError,
)
from rag.ai.models import RAGCitation, RAGResponse, RAGStreamEvent, RAGUsage
from rag.ai.rerank import ProviderReranker, build_reranker
from rag.ai.session import RAGSession

__all__ = [
    "CachedEmbedder",
    "EmbeddingCache",
    "NoChatProviderError",
    "ProviderReranker",
    "RAGCitation",
    "RAGConfiguration",
    "RAGConfigurationError",
    "RAGEngine",
    "RAGError",
    "RAGProviderError",
    "RAGResponse",
    "RAGSession",
    "RAGStreamEvent",
    "RAGUsage",
    "build_memory",
    "build_reranker",
    "build_retrieval_config",
]
