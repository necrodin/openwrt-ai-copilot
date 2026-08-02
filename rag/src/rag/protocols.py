"""Protocols for the Retrieval Core.

Every stage of the pipeline (``Question -> Embedding -> VectorStore -> Merge
Results -> Remove Duplicates -> Context Builder -> Prompt Builder -> Ready For
LLM``) is defined against these abstractions so the core stays provider- and
backend-independent. Concrete implementations live in the sibling modules and
can be swapped by configuration or dependency injection.

Types are intentionally small callables/ABCs — no provider SDKs, no LLM, no
streaming. Embedding and language detection are injected by the caller (the
``providers`` package later provides the real embedder).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any, Protocol

from rag.models import (
    ConversationState,
    MemorySnapshot,
    Message,
    PromptContext,
    PromptRequest,
    PromptResponse,
    RetrievedChunk,
)

#: Embed a text into a vector. The default is a single text -> vector callable;
#: ``providers`` exposes a batching ``EmbeddingFactory`` that satisfies this.
Embedder = Callable[[str], Awaitable[list[float]]]

#: Map a text to an ISO language code (e.g. ``en``). ``None`` disables detection.
LanguageDetector = Callable[[str], str] | None


class Retriever(ABC):
    """Turn a question into a ranked list of relevant chunks."""

    @abstractmethod
    async def retrieve(
        self,
        query: str,
        *,
        top_k: int | None = None,
        filters: list[Any] | None = None,
        namespace: str | None = None,
    ) -> list[RetrievedChunk]:
        """Return the most relevant chunks for ``query``, best first."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release any held resources (idempotent)."""


class ContextBuilder(ABC):
    """Assemble a :class:`PromptContext` from retrieved chunks + history."""

    @abstractmethod
    def build(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        history: list[Message] | None = None,
        language: str = "",
        system_prompt: str = "",
    ) -> PromptContext:
        """Group, rank, cite, and enrich the retrieved chunks into context."""


class Reranker(ABC):
    """Re-score retrieved chunks against the query, best first.

    Real implementations (e.g. NVIDIA NIM) are injected via the ``providers``
    package; :class:`rag.reranker.DummyReranker` preserves the vector-store
    order when no rerank-capable provider is configured.
    """

    @abstractmethod
    async def rerank(
        self,
        query: str,
        chunks: list[RetrievedChunk],
        *,
        top_n: int | None = None,
    ) -> list[RetrievedChunk]:
        """Return the top ``top_n`` chunks ordered by reranked relevance."""


class PromptBuilder(ABC):
    """Render a :class:`PromptContext` into a ready-for-LLM request."""

    @abstractmethod
    def build(self, context: PromptContext) -> PromptRequest:
        """Produce the final, LLM-ready :class:`PromptRequest`."""


class PromptOptimizer(ABC):
    """Reduce a prompt until it fits the configured token budget."""

    @abstractmethod
    def optimize(self, request: PromptRequest, max_prompt_tokens: int) -> PromptRequest:
        """Return a reduced prompt that fits within ``max_prompt_tokens``."""


class TokenEstimator(Protocol):
    """Estimate the number of tokens in a text."""

    def estimate(self, text: str) -> int: ...


class MemoryStore(ABC):
    """Persist :class:`ConversationState` objects keyed by conversation id."""

    @abstractmethod
    def get(self, conversation_id: str) -> ConversationState | None: ...

    @abstractmethod
    def list(self) -> list[ConversationState]: ...

    @abstractmethod
    def delete(self, conversation_id: str) -> bool: ...

    @abstractmethod
    def save(self, state: ConversationState) -> ConversationState: ...

    @abstractmethod
    def clear(self) -> None: ...


class ConversationMemory(ABC):
    """Rolling-window conversation memory with trimming and compression."""

    @abstractmethod
    def create(self, conversation_id: str, *, title: str = "") -> ConversationState: ...

    @abstractmethod
    def add(self, conversation_id: str, role: str, content: str) -> ConversationState: ...

    @abstractmethod
    def history(
        self,
        conversation_id: str,
        *,
        max_tokens: int | None = None,
    ) -> list[Message]: ...

    @abstractmethod
    def state(self, conversation_id: str) -> ConversationState | None: ...

    @abstractmethod
    def snapshot(self, conversation_id: str) -> MemorySnapshot | None: ...

    @abstractmethod
    def reset(self, conversation_id: str) -> None: ...


class ContextCache(ABC):
    """Cache for retrieval and prompt results (TTL + checksum keyed)."""

    @abstractmethod
    async def get_retrieval(self, key: str) -> list[RetrievedChunk] | None: ...

    @abstractmethod
    async def set_retrieval(self, key: str, chunks: list[RetrievedChunk]) -> None: ...

    @abstractmethod
    async def get_prompt(self, key: str) -> PromptResponse | None: ...

    @abstractmethod
    async def set_prompt(self, key: str, response: PromptResponse) -> None: ...

    @abstractmethod
    def invalidate(self, key_prefix: str = "") -> None: ...

    @abstractmethod
    def clear(self) -> None: ...


__all__ = [
    "ContextBuilder",
    "ContextCache",
    "ConversationMemory",
    "Embedder",
    "LanguageDetector",
    "MemoryStore",
    "PromptBuilder",
    "PromptOptimizer",
    "Reranker",
    "Retriever",
    "TokenEstimator",
]
