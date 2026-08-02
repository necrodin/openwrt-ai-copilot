"""VectorStore interface — the contract every backend adapter satisfies.

One interface, four backends (SQLite, Chroma, Qdrant, FAISS). Downstream code
(managers, future RAG) depends only on this abstraction.

Every method is async, takes a ``namespace`` (defaulting to the store's
configured default), and raises the :mod:`vectorstore.errors` hierarchy on
failure. ``score`` on results is always the cosine similarity (higher is
better).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from vectorstore.models import (
    CollectionInfo,
    CollectionStats,
    MetadataFilter,
    SearchRequest,
    SearchResult,
    VectorDocument,
    VectorMetadata,
)


class VectorStore(ABC):
    """Provider-independent vector database contract."""

    provider_type: str = "vectorstore"

    #: Configured instance name and default namespace, set per-instance in
    #: backends (kept as plain attributes so stores can assign them in
    #: ``__init__``).
    name: str = ""
    default_namespace: str = "default"

    @abstractmethod
    async def health(self) -> bool:
        """Return True when the backend is reachable and healthy."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release any held connections/resources."""

    # ------------------------------------------------------------------ #
    # Collections                                                        #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def create_collection(
        self,
        name: str,
        *,
        dimension: int,
        namespace: str | None = None,
        metadata: VectorMetadata | None = None,
    ) -> CollectionInfo:
        """Create a collection and return its :class:`CollectionInfo`.

        Raises :class:`CollectionExistsError` if it already exists in the
        namespace.
        """

    @abstractmethod
    async def delete_collection(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> None:
        """Delete a collection. Raises :class:`CollectionNotFoundError` when
        missing."""

    @abstractmethod
    async def list_collections(
        self,
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[CollectionInfo]:
        """List collections, optionally scoped to one namespace.

        ``namespace=None`` lists across every namespace; ``offset``/``limit``
        paginate.
        """

    @abstractmethod
    async def collection_info(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionInfo | None:
        """Return info for a collection, or ``None`` if it does not exist."""

    @abstractmethod
    async def stats(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionStats:
        """Aggregate statistics for a collection."""

    # ------------------------------------------------------------------ #
    # Documents                                                          #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def add_documents(
        self,
        name: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> list[str]:
        """Insert new documents; returns their ids.

        Raises :class:`VectorStoreError` if any id already exists (use
        :meth:`update_documents` to replace).
        """

    @abstractmethod
    async def update_documents(
        self,
        name: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> int:
        """Upsert documents; existing ids are replaced and their version
        incremented. Returns the number of documents written."""

    @abstractmethod
    async def delete_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
        """Delete documents by id; returns the number actually deleted."""

    @abstractmethod
    async def get_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> list[VectorDocument]:
        """Fetch documents by id, preserving the request order; missing ids are
        omitted."""

    # ------------------------------------------------------------------ #
    # Search                                                             #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def search(
        self,
        name: str,
        request: SearchRequest,
        *,
        namespace: str | None = None,
    ) -> list[SearchResult]:
        """Similarity search with optional metadata filters and pagination."""

    @abstractmethod
    async def filter_documents(
        self,
        name: str,
        filters: list[MetadataFilter],
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[VectorDocument]:
        """Metadata-only query; returns matching documents without ranking."""

    # ------------------------------------------------------------------ #
    # Metadata                                                           #
    # ------------------------------------------------------------------ #

    @abstractmethod
    async def set_metadata(
        self,
        name: str,
        id: str,
        metadata: VectorMetadata,
        *,
        namespace: str | None = None,
    ) -> None:
        """Replace a document's metadata (document must exist)."""

    @abstractmethod
    async def get_metadata(
        self,
        name: str,
        id: str,
        *,
        namespace: str | None = None,
    ) -> VectorMetadata:
        """Return a document's metadata. Raises
        :class:`DocumentNotFoundError` when missing."""


__all__ = ["VectorStore"]
