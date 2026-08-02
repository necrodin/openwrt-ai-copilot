"""Reusable data model for the vector database layer.

Every backend translates to/from these types, so downstream code (managers,
future RAG) only ever sees these shapes — never backend-specific payloads.

Semantics shared by every backend:

- ``score`` on :class:`SearchResult` is the **cosine similarity** (higher is
  better). The distance metric is fixed to ``cosine`` for this release.
- ``filters`` are AND-combined leaf clauses against document metadata.
- ``offset``/``limit`` paginate results (``limit=None`` means "no limit").
- ``version`` on :class:`VectorDocument` starts at ``1`` and is incremented
  every time the document is updated (upsert).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

FilterOperator = Literal["eq", "ne", "gt", "gte", "lt", "lte", "in", "not_in", "contains"]

DISTANCE_COSINE = "cosine"
SUPPORTED_DISTANCES: frozenset[str] = frozenset({DISTANCE_COSINE})

DEFAULT_NAMESPACE = "default"


class VectorMetadata(BaseModel):
    """Arbitrary key/value metadata attached to a vector document.

    Values must be JSON-serializable and filterable (str / int / float / bool /
    list of those). Stored on every document and used by metadata filters.
    """

    values: dict[str, Any] = Field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


class VectorDocument(BaseModel):
    """A stored vector plus its text, metadata, and version.

    ``id`` is opaque and backend-independent; ``vector`` is a plain list of
    floats. ``version`` is managed by the store: ``add_documents`` stores it
    as-is (default ``1``), ``update_documents`` bumps it on replacement.
    """

    id: str
    vector: list[float]
    text: str = ""
    metadata: VectorMetadata = Field(default_factory=VectorMetadata)
    version: int = 1


class MetadataFilter(BaseModel):
    """A single metadata filter clause (clauses are AND-combined)."""

    field: str
    op: FilterOperator = "eq"
    value: Any = None


class SearchRequest(BaseModel):
    """A similarity search against one collection.

    ``top_k`` is the candidate pool size fetched from the backend; ``offset``
    and ``limit`` paginate the returned results.
    """

    query_vector: list[float]
    top_k: int = 10
    filters: list[MetadataFilter] = Field(default_factory=list)
    offset: int = 0
    limit: int | None = None
    include_vectors: bool = False


class SearchResult(BaseModel):
    """One hit from a similarity search, ordered best-first."""

    id: str
    score: float
    text: str = ""
    metadata: VectorMetadata = Field(default_factory=VectorMetadata)
    vector: list[float] = Field(default_factory=list)
    version: int = 1


class CollectionInfo(BaseModel):
    """Descriptive metadata for a collection."""

    name: str
    namespace: str = DEFAULT_NAMESPACE
    dimension: int
    distance: str = DISTANCE_COSINE
    metadata: VectorMetadata = Field(default_factory=VectorMetadata)
    version: int = 1
    document_count: int = 0
    created_at: datetime | None = None


class CollectionStats(BaseModel):
    """Aggregate statistics for one collection."""

    name: str
    namespace: str = DEFAULT_NAMESPACE
    document_count: int = 0
    dimension: int = 0
    max_version: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None


__all__ = [
    "CollectionInfo",
    "CollectionStats",
    "DEFAULT_NAMESPACE",
    "DISTANCE_COSINE",
    "FilterOperator",
    "MetadataFilter",
    "SearchRequest",
    "SearchResult",
    "SUPPORTED_DISTANCES",
    "VectorDocument",
    "VectorMetadata",
]
