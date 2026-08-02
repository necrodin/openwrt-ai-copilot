"""High-level managers over a :class:`VectorStore`.

Thin, backend-independent facades that downstream code uses instead of calling
the store directly:

- :class:`CollectionManager` — collection lifecycle + statistics.
- :class:`DocumentManager` — document CRUD, batch insert, similarity search.
- :class:`MetadataManager` — per-document metadata and metadata-only queries.

All managers accept a ``namespace`` defaulting to the store's configured
default namespace.
"""

from __future__ import annotations

from vectorstore.errors import VectorStoreError
from vectorstore.models import (
    CollectionInfo,
    CollectionStats,
    MetadataFilter,
    SearchRequest,
    SearchResult,
    VectorDocument,
    VectorMetadata,
)
from vectorstore.protocols import VectorStore


def _namespace(store: VectorStore, namespace: str | None) -> str:
    return namespace or store.default_namespace


class CollectionManager:
    """Collection lifecycle and statistics."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    async def create(
        self,
        name: str,
        *,
        dimension: int,
        namespace: str | None = None,
        metadata: VectorMetadata | None = None,
    ) -> CollectionInfo:
        """Create a collection."""
        return await self.store.create_collection(
            name,
            dimension=dimension,
            namespace=_namespace(self.store, namespace),
            metadata=metadata,
        )

    async def delete(self, name: str, *, namespace: str | None = None) -> None:
        """Delete a collection (raises if missing)."""
        await self.store.delete_collection(name, namespace=_namespace(self.store, namespace))

    async def list(
        self,
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[CollectionInfo]:
        """List collections (``namespace=None`` lists across namespaces)."""
        return await self.store.list_collections(
            namespace=namespace,
            offset=offset,
            limit=limit,
        )

    async def info(self, name: str, *, namespace: str | None = None) -> CollectionInfo | None:
        """Return a collection's info, or ``None`` if it does not exist."""
        return await self.store.collection_info(name, namespace=_namespace(self.store, namespace))

    async def stats(self, name: str, *, namespace: str | None = None) -> CollectionStats:
        """Return aggregate statistics for a collection."""
        return await self.store.stats(name, namespace=_namespace(self.store, namespace))


class DocumentManager:
    """Document CRUD, batch insert, and similarity search."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    async def add(
        self,
        collection: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> list[str]:
        """Insert documents (batch); returns their ids."""
        return await self.store.add_documents(
            collection,
            documents,
            namespace=_namespace(self.store, namespace),
        )

    async def update(
        self,
        collection: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> int:
        """Upsert documents (existing ids are versioned up)."""
        return await self.store.update_documents(
            collection,
            documents,
            namespace=_namespace(self.store, namespace),
        )

    async def delete(
        self,
        collection: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
        """Delete documents by id; returns the number deleted."""
        return await self.store.delete_documents(
            collection,
            ids,
            namespace=_namespace(self.store, namespace),
        )

    async def get(
        self,
        collection: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> list[VectorDocument]:
        """Fetch documents by id (missing ids are omitted)."""
        return await self.store.get_documents(
            collection,
            ids,
            namespace=_namespace(self.store, namespace),
        )

    async def search(
        self,
        collection: str,
        query_vector: list[float],
        *,
        namespace: str | None = None,
        top_k: int = 10,
        filters: list[MetadataFilter] | None = None,
        offset: int = 0,
        limit: int | None = None,
        include_vectors: bool = False,
    ) -> list[SearchResult]:
        """Similarity search with optional filters and pagination."""
        request = SearchRequest(
            query_vector=query_vector,
            top_k=top_k,
            filters=filters or [],
            offset=offset,
            limit=limit,
            include_vectors=include_vectors,
        )
        return await self.store.search(
            collection,
            request,
            namespace=_namespace(self.store, namespace),
        )


class MetadataManager:
    """Per-document metadata and metadata-only queries."""

    def __init__(self, store: VectorStore) -> None:
        self.store = store

    async def set(
        self,
        collection: str,
        id: str,
        metadata: VectorMetadata,
        *,
        namespace: str | None = None,
        merge: bool = True,
    ) -> None:
        """Set a document's metadata.

        ``merge=True`` (default) merges into existing metadata; ``merge=False``
        replaces it entirely.
        """
        ns = _namespace(self.store, namespace)
        if merge:
            existing = await self.store.get_metadata(collection, id, namespace=ns)
            merged = VectorMetadata(values={**existing.to_dict(), **metadata.to_dict()})
            await self.store.set_metadata(collection, id, merged, namespace=ns)
        else:
            await self.store.set_metadata(collection, id, metadata, namespace=ns)

    async def get(
        self,
        collection: str,
        id: str,
        *,
        namespace: str | None = None,
    ) -> VectorMetadata:
        """Return a document's metadata (raises if the document is missing)."""
        return await self.store.get_metadata(
            collection, id, namespace=_namespace(self.store, namespace)
        )

    async def filter(
        self,
        collection: str,
        filters: list[MetadataFilter],
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[VectorDocument]:
        """Return documents matching every filter clause, without ranking."""
        return await self.store.filter_documents(
            collection,
            filters,
            namespace=_namespace(self.store, namespace),
            offset=offset,
            limit=limit,
        )


__all__ = [
    "CollectionManager",
    "DocumentManager",
    "MetadataManager",
    "VectorStoreError",
]
