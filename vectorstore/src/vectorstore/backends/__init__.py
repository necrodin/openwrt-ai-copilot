"""Vector store backends.

Every backend exposes the exact same :class:`VectorStore` API:
``sqlite`` (reference, offline), ``qdrant`` and ``chroma`` (HTTP REST, no SDK),
``faiss`` (optional in-process).
"""

from vectorstore.backends.chroma import ChromaVectorStore
from vectorstore.backends.faiss import FAISSVectorStore
from vectorstore.backends.qdrant import QdrantVectorStore
from vectorstore.backends.sqlite import SQLiteVectorStore

__all__ = [
    "ChromaVectorStore",
    "FAISSVectorStore",
    "QdrantVectorStore",
    "SQLiteVectorStore",
]
