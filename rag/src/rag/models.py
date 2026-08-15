"""Data models for the Retrieval Core.

These are the provider-independent shapes produced and consumed by the
retrieval pipeline — never backend payloads. The pipeline is:

``Question -> Embedding -> VectorStore -> Merge Results -> Remove Duplicates
-> Context Builder -> Prompt Builder -> Ready For LLM``

Every model here is a plain ``pydantic`` model so it serialises cleanly, plays
well with the rest of the monorepo, and can be cached/checksummed deterministically.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field

Role = Literal["system", "user", "assistant"]


def _utcnow() -> datetime:
    return datetime.now(UTC)


class Message(BaseModel):
    """A single conversation message in the Retrieval Core's own vocabulary.

    This is intentionally *not* tied to the AI-layer ``ChatMessage`` — the LLM
    layer stays free to map it to whatever provider format it needs. Kept
    minimal: role + content.
    """

    role: Role = "user"
    content: str = ""

    @property
    def token_estimate(self) -> int:
        """Cheap length proxy used until a real tokenizer is available."""
        return max(1, len(self.content) // 4)


class RetrievedChunk(BaseModel):
    """A single retrieved chunk with provenance and relevance.

    ``id`` follows the knowledge convention ``<document_id>#<index>``; ``score``
    is the post-normalisation relevance (0..1, higher is better); ``rank`` is
    the final 1-based position in the merged result list.
    """

    id: str
    document_id: str
    index: int
    text: str
    heading: str = ""
    score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)
    rank: int | None = None

    @classmethod
    def parse_id(cls, chunk_id: str) -> tuple[str, int] | None:
        """Split ``<document_id>#<index>`` back into its parts."""
        if "#" not in chunk_id:
            return None
        document_id, _, raw_index = chunk_id.rpartition("#")
        try:
            return document_id, int(raw_index)
        except ValueError:
            return None


class RetrievedDocument(BaseModel):
    """A retrieved knowledge document: metadata plus its selected chunks."""

    document_id: str
    title: str = ""
    source: str = ""
    reference: str = ""
    format: str = ""
    language: str = ""
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    best_score: float = 0.0
    checksum: str = ""
    version: int = 1

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


class Citation(BaseModel):
    """A numbered reference the prompt tells the LLM to reproduce.

    ``number`` is the 1-based index in the prompt (``[1]``, ``[2]``, ...);
    ``chunk_ids`` lists the retrieved chunks backing this citation; ``snippet``
    is a short quote so the citation stays meaningful even when the underlying
    source is not directly visible in the prompt.
    """

    number: int
    document_id: str
    chunk_ids: list[str] = Field(default_factory=list)
    source: str = ""
    reference: str = ""
    title: str = ""
    format: str = ""
    snippet: str = ""


class PromptContext(BaseModel):
    """The assembled context handed to the prompt builder.

    Holds everything the LLM may need: retrieved documents/chunks, citations,
    conversation history, language, and a system prompt override.
    """

    query: str
    chunks: list[RetrievedChunk] = Field(default_factory=list)
    documents: list[RetrievedDocument] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)
    history: list[Message] = Field(default_factory=list)
    language: str = ""
    system_prompt: str = ""
    token_estimate: int = 0


class TokenCounts(BaseModel):
    """Token accounting for a built prompt."""

    prompt_tokens: int = 0
    context_tokens: int = 0
    history_tokens: int = 0
    max_tokens: int = 0


class PromptRequest(BaseModel):
    """The final, LLM-ready request — the last stage of the pipeline.

    ``messages`` are the concrete messages that would be sent to a chat model
    (``system`` is embedded in :attr:`system`, history follows, and the final
    ``user`` message contains the context block plus the question). The AI layer
    maps these to its provider format.
    """

    request_id: str = Field(default_factory=lambda: str(uuid4()))
    query: str
    system: str = ""
    messages: list[Message] = Field(default_factory=list)
    context: PromptContext | None = None
    max_tokens: int = 0
    token_estimate: int = 0
    checksum: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    def is_within_budget(self, max_prompt_tokens: int) -> bool:
        """True when this request fits the given prompt-token budget."""
        return self.token_estimate <= max_prompt_tokens


class PromptResponse(BaseModel):
    """Result of the retrieval pipeline: everything needed to call an LLM."""

    request_id: str
    query: str
    prompt: PromptRequest
    tokens: TokenCounts = Field(default_factory=TokenCounts)
    cached: bool = False
    cache_key: str = ""
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def message_text(self) -> str:
        """Join the prompt's messages into one display string (debug/diffs)."""
        return "\n\n".join(f"{m.role}: {m.content}" for m in self.prompt.messages)


class MemorySnapshot(BaseModel):
    """A compressed summary of older conversation turns.

    Produced when the rolling window trims messages that no longer fit in the
    token budget; kept alongside the live window so context is never lost
    entirely.
    """

    snapshot_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    summary: str = ""
    keywords: list[str] = Field(default_factory=list)
    message_ids: list[str] = Field(default_factory=list)
    token_count: int = 0
    created_at: datetime = Field(default_factory=_utcnow)


class ConversationState(BaseModel):
    """Persistent state for one conversation: live window + compressed memory."""

    conversation_id: str
    title: str = ""
    messages: list[Message] = Field(default_factory=list)
    snapshots: list[MemorySnapshot] = Field(default_factory=list)
    token_count: int = 0
    #: Turns added since the last compression (drives snapshot cadence).
    pending_turns: int = 0
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


__all__ = [
    "Citation",
    "ConversationState",
    "MemorySnapshot",
    "Message",
    "PromptContext",
    "PromptRequest",
    "PromptResponse",
    "RetrievedChunk",
    "RetrievedDocument",
    "Role",
    "TokenCounts",
]
