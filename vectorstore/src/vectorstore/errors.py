"""Error hierarchy for vector store operations.

Backends raise these errors so callers handle failures uniformly regardless of
which backend produced them.
"""


class VectorStoreError(Exception):
    """Base class for all vector store errors."""


class VectorStoreConnectionError(VectorStoreError):
    """The backend could not be reached (network / I/O failure)."""


class VectorStoreAuthError(VectorStoreError):
    """The backend rejected the credentials."""


class CollectionNotFoundError(VectorStoreError):
    """The requested collection does not exist."""


class CollectionExistsError(VectorStoreError):
    """A collection with the same name already exists in the namespace."""


class DimensionMismatchError(VectorStoreError):
    """A document vector does not match the collection's dimension."""


class DocumentNotFoundError(VectorStoreError):
    """The requested document does not exist in the collection."""


class InvalidMetadataFilterError(VectorStoreError):
    """A metadata filter clause references a bad operator or value."""


__all__ = [
    "CollectionExistsError",
    "CollectionNotFoundError",
    "DimensionMismatchError",
    "DocumentNotFoundError",
    "InvalidMetadataFilterError",
    "VectorStoreAuthError",
    "VectorStoreConnectionError",
    "VectorStoreError",
]
