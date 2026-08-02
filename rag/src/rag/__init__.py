"""OpenWrt AI Copilot — Retrieval Core.

Sprint 9A: provider-independent retrieval pipeline — retrieval, context
building, prompt building, citations, conversation memory, token budgeting,
and caching. No LLM connection, no streaming; the pipeline ends at a ready
``PromptRequest``/``PromptResponse`` that a later sprint hands to the AI layer.

Pipeline: ``Question -> Embedding -> VectorStore -> Merge Results -> Remove
Duplicates -> Context Builder -> Prompt Builder -> Ready For LLM``.

The package depends only on the ``vectorstore`` interface plus its own modules;
embedding and language detection are injected callables, keeping the core
provider-independent.
"""

from __future__ import annotations

from rag.cache import InMemoryContextCache
from rag.citations import DefaultCitationBuilder
from rag.config import (
    CacheConfig,
    CollectionRef,
    ContextConfig,
    MemoryConfig,
    RetrievalConfig,
    TokenBudgetConfig,
)
from rag.context import DefaultContextBuilder
from rag.engine import RetrievalEngine
from rag.errors import (
    CacheError,
    CollectionError,
    ConfigurationError,
    ContextLimitError,
    EmbeddingError,
    MemoryError,
    RetrievalError,
    RetrieverError,
)
from rag.memory import (
    ConversationManager,
    InMemoryMemoryStore,
    RollingConversationMemory,
    summarize_messages,
)
from rag.models import (
    Citation,
    ConversationState,
    MemorySnapshot,
    Message,
    PromptContext,
    PromptRequest,
    PromptResponse,
    RetrievedChunk,
    RetrievedDocument,
    TokenCounts,
)
from rag.prompt import DefaultPromptBuilder, DefaultPromptOptimizer
from rag.retriever import VectorRetriever
from rag.tokens import HeuristicTokenEstimator, TokenBudgetManager

__version__ = "0.5.0-alpha"

__all__ = [
    "CacheConfig",
    "CacheError",
    "Citation",
    "CollectionError",
    "CollectionRef",
    "ConfigurationError",
    "ContextConfig",
    "ContextLimitError",
    "ConversationManager",
    "ConversationState",
    "DefaultCitationBuilder",
    "DefaultContextBuilder",
    "DefaultPromptBuilder",
    "DefaultPromptOptimizer",
    "EmbeddingError",
    "HeuristicTokenEstimator",
    "InMemoryContextCache",
    "InMemoryMemoryStore",
    "MemoryConfig",
    "MemoryError",
    "MemorySnapshot",
    "Message",
    "PromptContext",
    "PromptRequest",
    "PromptResponse",
    "RetrievalConfig",
    "RetrievalEngine",
    "RetrievalError",
    "RetrievedChunk",
    "RetrievedDocument",
    "RetrieverError",
    "RollingConversationMemory",
    "TokenBudgetConfig",
    "TokenBudgetManager",
    "TokenCounts",
    "VectorRetriever",
    "summarize_messages",
]
