"""Configuration for the Retrieval Core.

Configuration is declarative and provider-independent: switch collections,
budgets, memory, and caching behaviour through configuration rather than code.
A :class:`RetrievalConfig` can be built in code, from a dict, or from a YAML
file (the project already ships ``pyyaml``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from vectorstore.models import DEFAULT_NAMESPACE

DEFAULT_COLLECTION = "documents"


class CollectionRef(BaseModel):
    """A collection to search, with an optional merge weight."""

    name: str = DEFAULT_COLLECTION
    namespace: str = DEFAULT_NAMESPACE
    weight: float = 1.0


class TokenBudgetConfig(BaseModel):
    """Token budget used by the pipeline.

    - ``max_context_tokens``: hard ceiling for the *assembled context*
      (retrieved chunks + history + citations) before prompting.
    - ``max_prompt_tokens``: ceiling for the final prompt (system + history +
      context + query).
    - ``reserved_output_tokens``: tokens kept aside for the model's answer.
    - ``max_documents`` / ``max_chunks_per_document``: caps the context size.
    - ``max_history_tokens``: cap for conversation history in the prompt.
    """

    max_context_tokens: int = 6000
    max_prompt_tokens: int = 4000
    reserved_output_tokens: int = 1000
    max_documents: int = 6
    max_chunks_per_document: int = 3
    max_history_tokens: int = 1500


class MemoryConfig(BaseModel):
    """Rolling-window conversation memory settings."""

    enabled: bool = True
    window_size: int = 20
    max_snapshots: int = 8
    compress_threshold: int = 30


class CacheConfig(BaseModel):
    """Retrieval and prompt caching settings (TTL in seconds)."""

    enabled: bool = True
    retrieval_ttl_seconds: int = 300
    prompt_ttl_seconds: int = 60
    max_entries: int = 512


class ContextConfig(BaseModel):
    """Context-builder behaviour."""

    system_prompt: str = ""
    include_citations: bool = True
    citation_style: str = "numbered"


class RetrievalConfig(BaseModel):
    """Top-level configuration for the Retrieval Core."""

    collections: list[CollectionRef] = Field(default_factory=list)
    default_top_k: int = 8
    score_threshold: float | None = None
    deduplicate_by_text: bool = True
    namespace: str | None = None

    budget: TokenBudgetConfig = Field(default_factory=TokenBudgetConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    cache: CacheConfig = Field(default_factory=CacheConfig)
    context: ContextConfig = Field(default_factory=ContextConfig)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RetrievalConfig:
        """Build a config from a (possibly partial) dict."""
        return cls(**data)

    @classmethod
    def from_file(cls, path: str | Path) -> RetrievalConfig:
        """Load a config from a YAML file."""
        import yaml

        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw) or {}
        return cls.from_dict(data)


__all__ = [
    "CacheConfig",
    "CollectionRef",
    "ContextConfig",
    "DEFAULT_COLLECTION",
    "MemoryConfig",
    "RetrievalConfig",
    "TokenBudgetConfig",
]
