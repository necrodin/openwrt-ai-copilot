"""OpenWrt AI knowledge platform — provider-independent knowledge ingestion.

The knowledge platform turns documentation sources into chunked, versioned,
metadata-rich documents, independent of any AI provider or vector store:

    source → loader → parser → extractor → chunker → indexer

Everything is registered in :class:`KnowledgeRegistry`; built-in sources,
loaders, parsers, chunk strategies, extractors, and indexers register
themselves automatically. The high-level entry point is
:class:`KnowledgeManager`, driven by :class:`KnowledgePlatformConfig`.
"""

from __future__ import annotations

from knowledge.checksum import chunk_checksum, document_checksum, sha256_hex
from knowledge.config import (
    ChunkingConfig,
    KnowledgeCollectionConfig,
    KnowledgePlatformConfig,
)
from knowledge.errors import (
    KnowledgeError,
    KnowledgeExtractionError,
    KnowledgeIndexError,
    KnowledgeLoaderError,
    KnowledgeParseError,
    KnowledgeSourceError,
    UnsupportedFormatError,
)
from knowledge.manager import KnowledgeManager
from knowledge.models import (
    IndexResult,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeMetadata,
    KnowledgeVersion,
)
from knowledge.registry import KnowledgeRegistry, KnowledgeRegistryError

__version__ = "1.0.0"

__all__ = [
    "ChunkingConfig",
    "IndexResult",
    "KnowledgeChunk",
    "KnowledgeCollection",
    "KnowledgeCollectionConfig",
    "KnowledgeDocument",
    "KnowledgeError",
    "KnowledgeExtractionError",
    "KnowledgeIndexError",
    "KnowledgeLoaderError",
    "KnowledgeManager",
    "KnowledgeMetadata",
    "KnowledgeParseError",
    "KnowledgePlatformConfig",
    "KnowledgeRegistry",
    "KnowledgeRegistryError",
    "KnowledgeSourceError",
    "KnowledgeVersion",
    "UnsupportedFormatError",
    "chunk_checksum",
    "document_checksum",
    "sha256_hex",
]
