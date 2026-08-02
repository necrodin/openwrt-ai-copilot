"""Knowledge registry — a thread-safe catalog of every knowledge component.

Sources, loaders, parsers (keyed by format), chunk strategies, metadata
extractors, and indexers register here. The registry is pure catalog: it holds
no AI logic and no format logic. Built-in implementations register themselves
on first use via :meth:`KnowledgeRegistry.register_builtins`.
"""

from __future__ import annotations

import threading

from knowledge.errors import KnowledgeError, UnsupportedFormatError
from knowledge.protocols import (
    ChunkStrategy,
    KnowledgeIndexer,
    KnowledgeLoader,
    KnowledgeParser,
    KnowledgeSource,
    MetadataExtractor,
)


class KnowledgeRegistryError(KnowledgeError):
    """A registry operation failed (missing / duplicate entry)."""


class KnowledgeRegistry:
    """Thread-safe registry of knowledge platform components."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._sources: dict[str, KnowledgeSource] = {}
        self._loaders: dict[str, KnowledgeLoader] = {}
        self._parsers: dict[str, KnowledgeParser] = {}
        self._chunkers: dict[str, ChunkStrategy] = {}
        self._extractors: dict[str, MetadataExtractor] = {}
        self._indexers: dict[str, KnowledgeIndexer] = {}

    # ------------------------------------------------------------------ #
    # Sources                                                            #
    # ------------------------------------------------------------------ #

    def register_source(self, source: KnowledgeSource, *, replace: bool = False) -> None:
        with self._lock:
            if source.id in self._sources and not replace:
                raise KnowledgeRegistryError(f"Knowledge source {source.id!r} already registered")
            self._sources[source.id] = source

    def unregister_source(self, source_id: str) -> None:
        with self._lock:
            self._sources.pop(source_id, None)

    def get_source(self, source_id: str) -> KnowledgeSource:
        with self._lock:
            try:
                return self._sources[source_id]
            except KeyError as exc:
                message = f"Knowledge source {source_id!r} is not registered"
                raise KnowledgeRegistryError(message) from exc

    def sources(self) -> list[KnowledgeSource]:
        with self._lock:
            return sorted(self._sources.values(), key=lambda source: source.id)

    # ------------------------------------------------------------------ #
    # Loaders                                                            #
    # ------------------------------------------------------------------ #

    def register_loader(
        self, loader: KnowledgeLoader, *, loader_type: str | None = None, replace: bool = False
    ) -> None:
        key = loader_type or loader.loader_type
        with self._lock:
            if key in self._loaders and not replace:
                raise KnowledgeRegistryError(f"Knowledge loader {key!r} already registered")
            self._loaders[key] = loader

    def get_loader(self, loader_type: str) -> KnowledgeLoader:
        with self._lock:
            try:
                return self._loaders[loader_type]
            except KeyError as exc:
                message = f"Knowledge loader {loader_type!r} is not registered"
                raise KnowledgeRegistryError(message) from exc

    def loaders(self) -> list[str]:
        with self._lock:
            return sorted(self._loaders)

    # ------------------------------------------------------------------ #
    # Parsers (keyed by format)                                          #
    # ------------------------------------------------------------------ #

    def register_parser(self, parser: KnowledgeParser, *, replace: bool = False) -> None:
        with self._lock:
            if parser.format in self._parsers and not replace:
                message = f"Knowledge parser for {parser.format!r} already registered"
                raise KnowledgeRegistryError(message)
            self._parsers[parser.format] = parser

    def get_parser(self, format: str) -> KnowledgeParser:
        with self._lock:
            try:
                return self._parsers[format.lower()]
            except KeyError as exc:
                raise UnsupportedFormatError(
                    f"No knowledge parser for format {format!r}; "
                    f"registered: {', '.join(sorted(self._parsers)) or 'none'}"
                ) from exc

    def parsers(self) -> list[str]:
        with self._lock:
            return sorted(self._parsers)

    # ------------------------------------------------------------------ #
    # Chunk strategies                                                   #
    # ------------------------------------------------------------------ #

    def register_chunker(
        self, chunker: ChunkStrategy, *, strategy_type: str | None = None, replace: bool = False
    ) -> None:
        key = strategy_type or chunker.strategy_type
        with self._lock:
            if key in self._chunkers and not replace:
                raise KnowledgeRegistryError(f"Chunk strategy {key!r} already registered")
            self._chunkers[key] = chunker

    def get_chunker(self, strategy_type: str) -> ChunkStrategy:
        with self._lock:
            try:
                return self._chunkers[strategy_type]
            except KeyError as exc:
                message = f"Chunk strategy {strategy_type!r} is not registered"
                raise KnowledgeRegistryError(message) from exc

    def chunkers(self) -> list[str]:
        with self._lock:
            return sorted(self._chunkers)

    # ------------------------------------------------------------------ #
    # Metadata extractors                                                #
    # ------------------------------------------------------------------ #

    def register_extractor(
        self,
        extractor: MetadataExtractor,
        *,
        extractor_type: str | None = None,
        replace: bool = False,
    ) -> None:
        key = extractor_type or extractor.extractor_type
        with self._lock:
            if key in self._extractors and not replace:
                raise KnowledgeRegistryError(f"Metadata extractor {key!r} already registered")
            self._extractors[key] = extractor

    def get_extractor(self, extractor_type: str) -> MetadataExtractor:
        with self._lock:
            try:
                return self._extractors[extractor_type]
            except KeyError as exc:
                raise KnowledgeRegistryError(
                    f"Metadata extractor {extractor_type!r} is not registered"
                ) from exc

    def extractors(self) -> list[str]:
        with self._lock:
            return sorted(self._extractors)

    # ------------------------------------------------------------------ #
    # Indexers                                                           #
    # ------------------------------------------------------------------ #

    def register_indexer(
        self, indexer: KnowledgeIndexer, *, indexer_type: str | None = None, replace: bool = False
    ) -> None:
        key = indexer_type or indexer.indexer_type
        with self._lock:
            if key in self._indexers and not replace:
                raise KnowledgeRegistryError(f"Knowledge indexer {key!r} already registered")
            self._indexers[key] = indexer

    def get_indexer(self, indexer_type: str) -> KnowledgeIndexer:
        with self._lock:
            try:
                return self._indexers[indexer_type]
            except KeyError as exc:
                message = f"Knowledge indexer {indexer_type!r} is not registered"
                raise KnowledgeRegistryError(message) from exc

    def indexers(self) -> list[str]:
        with self._lock:
            return sorted(self._indexers)

    # ------------------------------------------------------------------ #
    # Built-ins                                                          #
    # ------------------------------------------------------------------ #

    def register_builtins(self) -> None:
        """Register every shipped implementation (idempotent).

        Only registers a built-in when the corresponding key is not already
        registered, so user-registered components with the same id/format are
        never replaced.
        """
        from knowledge.chunking import (
            FixedSizeChunkStrategy,
            HeadingChunkStrategy,
            ParagraphChunkStrategy,
            SlidingWindowChunkStrategy,
        )
        from knowledge.extractors import (
            HeadingExtractor,
            LanguageExtractor,
            SourceExtractor,
            StatsExtractor,
            TitleExtractor,
        )
        from knowledge.indexer import FileSystemKnowledgeIndexer, InMemoryKnowledgeIndexer
        from knowledge.loaders import DirectoryLoader, FileLoader, TextLoader
        from knowledge.parsers import (
            HtmlParser,
            JsonParser,
            MarkdownParser,
            PdfParser,
            TextParser,
            XmlParser,
            YamlParser,
        )
        from knowledge.sources import OpenWrtKnowledgeSource, StaticSource

        with self._lock:
            if "openwrt" not in self._sources:
                self.register_source(OpenWrtKnowledgeSource())
            if "static" not in self._sources:
                self.register_source(StaticSource("static"))

            if "text" not in self._loaders:
                self.register_loader(TextLoader())
            if "file" not in self._loaders:
                self.register_loader(FileLoader())
            if "directory" not in self._loaders:
                self.register_loader(DirectoryLoader())

            for parser in (
                MarkdownParser(),
                HtmlParser(),
                PdfParser(),
                TextParser(),
                JsonParser(),
                YamlParser(),
                XmlParser(),
            ):
                if parser.format not in self._parsers:
                    self.register_parser(parser)

            builtin_chunkers = (
                FixedSizeChunkStrategy(300),
                SlidingWindowChunkStrategy(300),
                HeadingChunkStrategy(300),
                ParagraphChunkStrategy(),
            )
            for chunker in builtin_chunkers:
                if chunker.strategy_type not in self._chunkers:
                    self.register_chunker(chunker)

            builtin_extractors = (
                TitleExtractor(),
                HeadingExtractor(),
                LanguageExtractor(),
                SourceExtractor(),
                StatsExtractor(),
            )
            for extractor in builtin_extractors:
                if extractor.extractor_type not in self._extractors:
                    self.register_extractor(extractor)

            if "memory" not in self._indexers:
                self.register_indexer(InMemoryKnowledgeIndexer())
            if "filesystem" not in self._indexers:
                self.register_indexer(FileSystemKnowledgeIndexer(""))

    def clear(self) -> None:
        with self._lock:
            self._sources.clear()
            self._loaders.clear()
            self._parsers.clear()
            self._chunkers.clear()
            self._extractors.clear()
            self._indexers.clear()


__all__ = ["KnowledgeRegistry", "KnowledgeRegistryError"]
