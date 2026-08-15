"""OpenWrt AI Copilot — provider-independent vector database layer.

Defines a single :class:`VectorStore` interface plus reusable models
(``VectorDocument``, ``SearchRequest``, ``CollectionInfo`` …), a
:class:`VectorStoreFactory`, and high-level managers (:class:`CollectionManager`,
:class:`DocumentManager`, :class:`MetadataManager`).

Backends — SQLite (reference, offline), Chroma, Qdrant, FAISS — all expose the
exact same API. The package never imports a vendor SDK: Chroma and Qdrant are
driven through their documented HTTP REST APIs, FAISS is an optional in-process
backend. Future RAG builds on this abstraction only.
"""

from __future__ import annotations

__version__ = "1.0.0"

from vectorstore.config import (
    DEFAULT_STORE_TYPES,
    SUPPORTED_STORE_TYPES,
    VectorStoreConfig,
    VectorStoresConfig,
)
from vectorstore.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
    DocumentNotFoundError,
    InvalidMetadataFilterError,
    VectorStoreAuthError,
    VectorStoreConnectionError,
    VectorStoreError,
)
from vectorstore.factory import (
    VectorStoreFactory,
    available_store_types,
    create_store,
    register_store,
    unregister_store,
)
from vectorstore.managers import CollectionManager, DocumentManager, MetadataManager
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

__all__ = [
    "CollectionExistsError",
    "CollectionInfo",
    "CollectionManager",
    "CollectionNotFoundError",
    "CollectionStats",
    "DEFAULT_STORE_TYPES",
    "DimensionMismatchError",
    "DocumentManager",
    "DocumentNotFoundError",
    "InvalidMetadataFilterError",
    "MetadataFilter",
    "MetadataManager",
    "SUPPORTED_STORE_TYPES",
    "SearchRequest",
    "SearchResult",
    "VectorDocument",
    "VectorMetadata",
    "VectorStore",
    "VectorStoreAuthError",
    "VectorStoreConfig",
    "VectorStoreConnectionError",
    "VectorStoreError",
    "VectorStoreFactory",
    "VectorStoresConfig",
    "available_store_types",
    "create_store",
    "register_store",
    "unregister_store",
]
