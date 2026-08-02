"""Configuration for the RAG integration layer.

Declarative, provider-independent: tune retrieval breadth, grounding, provider
and reranker selection, temperature, and streaming through a single object that
can be built in code, from a dict, or from a YAML file (``rag.yaml``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from rag.config import DEFAULT_COLLECTION

_DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful network assistant for an OpenWrt router, grounded in "
    "the retrieved knowledge context.\n\n"
    "STRICT RULES:\n"
    "1. Answer ONLY from the context above, which is marked with numbered "
    "sources like [1], [2]. Never invent, guess, or assume facts that are not "
    "present in the context.\n"
    "2. Cite the source for each claim using [N] markers that match the "
    "numbered sources.\n"
    "3. If the answer is not derivable from the context, say so clearly and do "
    "not fabricate values.\n"
    "4. Format the answer with Markdown: short paragraphs, bullet lists, and "
    "`inline code` for commands, IPs, and paths. Use fenced code blocks where "
    "useful. Do not use emojis."
)


class RAGConfiguration(BaseModel):
    """Top-level configuration for grounded, cited chat."""

    #: Vector collection to search.
    collection: str = DEFAULT_COLLECTION
    #: Namespace within the collection (``None`` = store default).
    namespace: str | None = None
    #: Embedding dimensions the collection is created with (768 default).
    vector_dimensions: int = Field(default=768, ge=1)
    #: Candidate chunks retrieved from the vector store per query.
    top_k: int = Field(default=8, ge=1)
    #: Maximum source documents injected into the context.
    max_documents: int = Field(default=6, ge=1)
    #: Minimum similarity for a chunk to enter the context (0..1; ``None`` disables).
    score_threshold: float | None = Field(default=None, ge=0.0, le=1.0)

    #: Chat provider preference (name from providers.yaml) and model override.
    provider: str | None = None
    model: str | None = None
    #: Sampling temperature passed through to the chat provider.
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)

    #: Embedding provider/model used for the query vector.
    embed_provider: str | None = None
    embed_model: str | None = None

    #: Reranker selection. When both are empty the pipeline uses the vector-store
    #: order (deterministic dummy reranker); ``rerank_provider`` names a
    #: rerank-capable provider (e.g. ``nim``) and ``rerank_model`` its model.
    rerank_provider: str | None = None
    rerank_model: str | None = None

    #: System prompt overriding the grounded default (see :class:`RAGConfiguration`).
    system_prompt: str = ""

    #: Enable retrieval/prompt caching and conversation memory.
    use_cache: bool = True
    memory_enabled: bool = True
    memory_window: int = Field(default=20, ge=2)
    #: Allow the session to expand context on demand (see ``RAGSession.expand_context``).
    context_expansion: bool = True

    @property
    def effective_system_prompt(self) -> str:
        return self.system_prompt.strip() or _DEFAULT_SYSTEM_PROMPT

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RAGConfiguration:
        """Build a config from a (possibly partial) dict."""
        return cls(**data)

    @classmethod
    def from_file(cls, path: str | Path) -> RAGConfiguration:
        """Load a config from a YAML file."""
        import yaml

        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return cls.from_dict(data)


__all__ = ["RAGConfiguration"]
