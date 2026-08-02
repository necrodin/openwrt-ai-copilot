"""Response models for the RAG integration layer.

These are the shapes the chat feature consumes: a grounded, cited answer
(:class:`RAGResponse`) and the streaming event feed (:class:`RAGStreamEvent`).
Every citation carries the knowledge provenance the UI renders — knowledge
source, document name, section, chunk id, and confidence score.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

RAGStreamType = Literal[
    "session",
    "retrieval",
    "generation_started",
    "delta",
    "citations",
    "done",
    "error",
]


class RAGCitation(BaseModel):
    """A single knowledge source backing part of the answer."""

    #: Knowledge source, e.g. a docs path or knowledge-base name.
    source: str = ""
    #: Document name, e.g. ``wireguard.md``.
    document: str = ""
    #: Section/heading within the document.
    section: str = ""
    #: Chunk id following the convention ``<document_id>#<index>``.
    chunk_id: str
    #: Vector-store similarity (0..1, post normalisation).
    similarity_score: float = 0.0
    #: Rerank score (0..1) when a reranker was applied, else ``None``.
    rerank_score: float | None = None
    #: Relevance used for ranking/display (rerank score if present, else similarity).
    confidence: float = 0.0
    #: Short quoted excerpt so the citation is self-explanatory.
    snippet: str = ""


class RAGUsage(BaseModel):
    """Token and retrieval accounting for a RAG answer."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: Chunks actually injected into the context.
    chunks_retrieved: int = 0
    #: Chunks served from the retrieval/prompt cache.
    cached_chunks: int = 0
    #: Milliseconds spent in retrieval + prompt building.
    retrieval_ms: float = 0.0


class RAGResponse(BaseModel):
    """A complete, grounded chat answer with citations."""

    answer: str
    conversation_id: str
    citations: list[RAGCitation] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    usage: RAGUsage = Field(default_factory=RAGUsage)
    #: True when the underlying prompt was served from the cache.
    cached: bool = False


class RAGStreamEvent(BaseModel):
    """One Server-Sent event in a RAG chat stream.

    Event timeline: ``session`` (started) -> ``retrieval`` (context ready, with
    citations) -> ``generation_started`` -> ``delta`` (token stream, repeated) ->
    ``done`` (generation finished) — or ``error`` at any point.
    """

    type: RAGStreamType
    conversation_id: str = ""
    #: Delta text (type ``delta``) or the full reply (type ``done``).
    content: str = ""
    citations: list[RAGCitation] = Field(default_factory=list)
    provider: str = ""
    model: str = ""
    error: str = ""
    usage: RAGUsage = Field(default_factory=RAGUsage)


__all__ = [
    "RAGCitation",
    "RAGResponse",
    "RAGStreamEvent",
    "RAGUsage",
    "RAGStreamType",
]
