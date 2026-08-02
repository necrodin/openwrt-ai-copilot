"""OpenWrt AI Copilot — Retrieval Core.

Sprint 9A: provider-independent retrieval pipeline — retrieval, context
building, prompt building, citations, conversation memory, token budgeting,
and caching. No LLM connection, no streaming; the pipeline ends at a ready
``PromptRequest``/``PromptResponse`` that the AI layer (``rag.ai``) turns into
a grounded, cited answer.

Sprint 9B: a ``reranker`` hook (see :class:`rag.protocols.Reranker` and
:class:`rag.reranker.DummyReranker`) lets an injected reranker re-score
retrieved chunks before the context is built; the ``rag.ai`` subpackage
integrates the core with the ``providers`` package to produce answers.

Pipeline: ``Question -> Embedding -> VectorStore -> Merge Results -> Remove
Duplicates -> Rerank (optional) -> Context Builder -> Prompt Builder -> LLM``.

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
from rag.protocols import Reranker
from rag.reranker import DummyReranker
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
    "DummyReranker",
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
    "Reranker",
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
