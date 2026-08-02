"""Error hierarchy for the knowledge platform.

Sources, loaders, parsers, chunkers, extractors, and indexers raise these so
callers handle failures uniformly regardless of which implementation produced
them.
"""


class KnowledgeError(Exception):
    """Base class for all knowledge platform errors."""


class KnowledgeSourceError(KnowledgeError):
    """A knowledge source could not list or load its documents."""


class KnowledgeLoaderError(KnowledgeError):
    """A loader could not fetch raw content for a reference."""


class KnowledgeParseError(KnowledgeError):
    """A parser could not turn raw content into a document."""


class UnsupportedFormatError(KnowledgeParseError):
    """No parser is registered for the requested format."""


class KnowledgeChunkingError(KnowledgeError):
    """A chunk strategy could not split a document."""


class KnowledgeExtractionError(KnowledgeError):
    """A metadata extractor failed to produce metadata."""


class KnowledgeIndexError(KnowledgeError):
    """An indexer could not persist or reconcile index state."""


__all__ = [
    "KnowledgeChunkingError",
    "KnowledgeError",
    "KnowledgeExtractionError",
    "KnowledgeIndexError",
    "KnowledgeLoaderError",
    "KnowledgeParseError",
    "KnowledgeSourceError",
    "UnsupportedFormatError",
]
