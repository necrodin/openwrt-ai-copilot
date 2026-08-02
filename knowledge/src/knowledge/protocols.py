"""Knowledge platform interfaces.

Six small contracts, all provider-independent and vector-store-independent.
Downstream code (collections, managers, future RAG) depends only on these
abstractions:

- :class:`KnowledgeSource` — where knowledge lives (a wiki, a directory, …).
- :class:`KnowledgeLoader` — how raw content is fetched for a reference.
- :class:`KnowledgeParser` — how raw content in one format becomes a document.
- :class:`ChunkStrategy` — how a document is split into chunks.
- :class:`MetadataExtractor` — how metadata is derived from a document.
- :class:`KnowledgeIndexer` — how documents/chunks are stored incrementally.

The pipeline is: ``source -> loader -> parser -> extractor -> chunker ->
indexer``. Every step is swappable; nothing here imports a vendor SDK, the AI
provider layer, or the vector store.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeMetadata,
    KnowledgeVersion,
)


class KnowledgeSource(ABC):
    """A collection of knowledge documents (e.g. the OpenWrt wiki)."""

    source_type: str = "generic"
    formats: set[str] = set()

    @property
    @abstractmethod
    def id(self) -> str:
        """Stable source identifier (e.g. "openwrt-wiki")."""

    @property
    def description(self) -> str:
        return ""

    def list_documents(self) -> list[str]:
        """Return every document reference this source can provide.

        Sync by default; HTTP-backed sources override with an async
        ``list_documents_async``.
        """
        return []

    async def list_documents_async(self) -> list[str]:
        return self.list_documents()

    def load(self, reference: str) -> bytes:
        """Return raw content for a reference.

        Sync by default; HTTP-backed sources override with an async ``load_async``.
        """
        raise NotImplementedError

    async def load_async(self, reference: str) -> bytes:
        return self.load(reference)


class KnowledgeLoader(ABC):
    """Fetches raw content for a reference (a path, URL, or id)."""

    loader_type: str = "generic"

    @abstractmethod
    def load(self, reference: str) -> bytes:
        """Fetch raw bytes for a reference."""

    async def load_async(self, reference: str) -> bytes:
        return self.load(reference)


class KnowledgeParser(ABC):
    """Turns raw content of one format into a :class:`KnowledgeDocument`."""

    format: str = ""

    @abstractmethod
    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        """Parse raw content into a normalized document."""


class ChunkStrategy(ABC):
    """Splits a :class:`KnowledgeDocument` into :class:`KnowledgeChunk`\\ s."""

    strategy_type: str = "generic"

    @abstractmethod
    def chunk(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        """Split one document into chunks."""


class MetadataExtractor(ABC):
    """Derives :class:`KnowledgeMetadata` from a document."""

    extractor_type: str = "generic"

    @abstractmethod
    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        """Return metadata describing the document."""


class KnowledgeIndexer(ABC):
    """Stores documents/chunks incrementally with version + duplicate tracking."""

    indexer_type: str = "generic"

    @abstractmethod
    def exists(self, document_id: str) -> bool:
        """Whether the document is already indexed."""

    @abstractmethod
    def ingest(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
        *,
        collection_id: str,
    ) -> KnowledgeVersion:
        """Index a document (and its chunks) into a collection.

        Returns a :class:`KnowledgeVersion` describing what happened: the
        checksum decides between ``added``, ``updated``, ``unchanged``, and
        ``duplicate``.
        """

    @abstractmethod
    def reconcile(self, seen_ids: set[str], *, collection_id: str) -> list[KnowledgeVersion]:
        """Mark documents in a collection that were not seen as removed."""

    @abstractmethod
    def documents(self, collection_id: str) -> list[KnowledgeDocument]:
        """Return every indexed document in a collection."""

    @abstractmethod
    def chunks(self, document_id: str) -> list[KnowledgeChunk]:
        """Return the chunks of one document."""

    @abstractmethod
    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        """Return a single document, or ``None`` if missing."""

    @abstractmethod
    def collection(self, collection_id: str) -> KnowledgeCollection | None:
        """Return collection info, or ``None`` if missing."""

    @abstractmethod
    def collections(self) -> list[KnowledgeCollection]:
        """Return every known collection."""

    @abstractmethod
    def find_duplicates(self, collection_id: str) -> dict[str, list[str]]:
        """Map a checksum to every document id sharing it."""

    @abstractmethod
    def versions(self, collection_id: str) -> list[KnowledgeVersion]:
        """Return the version history for a collection."""

    @abstractmethod
    def flush(self) -> None:
        """Persist any in-memory state (no-op for in-memory indexers)."""


__all__ = [
    "ChunkStrategy",
    "KnowledgeIndexer",
    "KnowledgeLoader",
    "KnowledgeParser",
    "KnowledgeSource",
    "MetadataExtractor",
]
