"""Errors for the RAG integration layer (``rag.ai``)."""

from __future__ import annotations

from rag.errors import RetrievalError


class RAGError(RetrievalError):
    """Base error for the RAG integration layer."""


class RAGConfigurationError(RAGError):
    """Raised when the RAG configuration is invalid or cannot be loaded."""


class RAGProviderError(RAGError):
    """Raised when a required provider capability is missing or a call fails."""


class NoChatProviderError(RAGProviderError):
    """Raised when no chat-capable provider is available for an answer."""


__all__ = [
    "NoChatProviderError",
    "RAGConfigurationError",
    "RAGError",
    "RAGProviderError",
]
