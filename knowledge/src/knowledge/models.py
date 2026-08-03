"""Reusable data model for the knowledge platform.

These are the shapes every source, loader, parser, chunker, extractor, and
indexer translate to/from — downstream code (collections, future RAG) only ever
sees these types, never format-specific or source-specific payloads.

Lifecycle shared by every indexer:

- A :class:`KnowledgeDocument` is a single unit of knowledge (one file, one
  page). Its ``checksum`` is derived from the normalized text and is how
  change / duplicate detection works.
- A :class:`KnowledgeDocument` is split into :class:`KnowledgeChunk`\\ s by a
  :class:`ChunkStrategy`.
- :class:`KnowledgeVersion` records what happened to a document during one
  indexing pass (added / updated / unchanged / removed / duplicate).
- A :class:`KnowledgeCollection` groups indexed documents into a named corpus
  (e.g. "openwrt-wiki" or "wireguard").
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

#: Change kind produced by an indexing pass, one per document.
KnowledgeChange = Literal["added", "updated", "unchanged", "removed", "duplicate"]


class KnowledgeMetadata(BaseModel):
    """Arbitrary key/value metadata attached to a document or chunk.

    Values must be JSON-serializable (str / int / float / bool / list of
    those). Kept as a dict so sources, parsers, and extractors can attach
    whatever they learned without a fixed schema.
    """

    values: dict[str, Any] = Field(default_factory=dict)

    def get(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def __len__(self) -> int:
        return len(self.values)

    def __bool__(self) -> bool:
        return bool(self.values)

    def __contains__(self, key: object) -> bool:
        return key in self.values

    def to_dict(self) -> dict[str, Any]:
        return dict(self.values)

    def merge(self, other: KnowledgeMetadata) -> KnowledgeMetadata:
        """Return a new metadata with ``other``'s values overlaid."""
        merged = dict(self.values)
        merged.update(other.values)
        return KnowledgeMetadata(values=merged)

    def __getitem__(self, key: str) -> Any:
        return self.values[key]


class KnowledgeDocument(BaseModel):
    """A parsed, normalized knowledge document.

    ``text`` is the normalized plain text (what gets chunked). ``checksum`` is
    a stable digest of that normalized text; ``version`` is the document's
    version in its collection (bumped every time the checksum changes).
    """

    id: str
    source: str = ""
    reference: str = ""
    format: str = ""
    title: str = ""
    text: str = ""
    language: str = ""
    metadata: KnowledgeMetadata = Field(default_factory=KnowledgeMetadata)
    checksum: str = ""
    version: int = 1
    created_at: datetime | None = None

    @property
    def text_length(self) -> int:
        return len(self.text)


class KnowledgeChunk(BaseModel):
    """One chunk of a knowledge document."""

    id: str
    document_id: str
    index: int
    text: str = ""
    heading: str = ""
    metadata: KnowledgeMetadata = Field(default_factory=KnowledgeMetadata)
    checksum: str = ""


class KnowledgeCollection(BaseModel):
    """A named corpus of indexed documents (e.g. "wireguard")."""

    id: str
    name: str = ""
    description: str = ""
    document_ids: list[str] = Field(default_factory=list)
    chunk_count: int = 0
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None
    metadata: KnowledgeMetadata = Field(default_factory=KnowledgeMetadata)

    @property
    def document_count(self) -> int:
        return len(self.document_ids)


class KnowledgeVersion(BaseModel):
    """The outcome of one indexing pass for a document."""

    document_id: str
    version: int = 1
    checksum: str = ""
    change: KnowledgeChange = "added"
    source: str = ""
    indexed_at: datetime | None = None


class IndexResult(BaseModel):
    """Aggregate outcome of an indexing run (one source or collection)."""

    collection_id: str
    documents_seen: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    removed: int = 0
    duplicates: int = 0
    chunks_total: int = 0
    versions: list[KnowledgeVersion] = Field(default_factory=list)

    @property
    def changed(self) -> bool:
        return bool(self.added or self.updated or self.removed)


__all__ = [
    "IndexResult",
    "KnowledgeChange",
    "KnowledgeChunk",
    "KnowledgeCollection",
    "KnowledgeDocument",
    "KnowledgeMetadata",
    "KnowledgeVersion",
]
