"""KnowledgeManager — the high-level knowledge platform facade.

Composes the registry's sources, loaders, parsers, chunkers, extractors, and
indexers into an end-to-end ingestion pipeline:

    source → loader → parser → extractor → chunker → indexer

The manager is provider-independent and vector-store-independent: it never
imports the AI provider layer or the vector store, so the same code builds a
knowledge base from the OpenWrt wiki, local files, or in-memory snippets.

Typical usage::

    manager = KnowledgeManager(registry, config)
    await manager.index_collection("wireguard")
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge.config import (
    ChunkingConfig,
    KnowledgeCollectionConfig,
    KnowledgePlatformConfig,
)
from knowledge.errors import KnowledgeSourceError
from knowledge.models import (
    IndexResult,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeVersion,
)
from knowledge.protocols import (
    KnowledgeIndexer,
    KnowledgeLoader,
    KnowledgeParser,
    KnowledgeSource,
    MetadataExtractor,
)
from knowledge.registry import KnowledgeRegistry


def _load_sync_or_async(loader: KnowledgeLoader, reference: str) -> bytes:
    try:
        return loader.load(reference)
    except NotImplementedError:
        import asyncio

        return asyncio.run(loader.load_async(reference))


class KnowledgeManager:
    """Ingest knowledge sources into an indexer, collection by collection."""

    def __init__(
        self,
        registry: KnowledgeRegistry | None = None,
        config: KnowledgePlatformConfig | None = None,
    ) -> None:
        self.registry = registry or KnowledgeRegistry()
        self.registry.register_builtins()
        self.config = config or KnowledgePlatformConfig()
        self._indexer: KnowledgeIndexer = self._build_indexer()
        self._extractor: MetadataExtractor = self._build_extractor()

    # ------------------------------------------------------------------ #
    # Construction                                                       #
    # ------------------------------------------------------------------ #

    def _build_indexer(self) -> KnowledgeIndexer:
        if self.config.indexer_type == "filesystem":
            from knowledge.indexer import FileSystemKnowledgeIndexer

            return FileSystemKnowledgeIndexer(self.config.indexer_path)
        return self.registry.get_indexer("memory")

    def _build_extractor(self) -> MetadataExtractor:
        from knowledge.extractors import CompositeMetadataExtractor

        composite = CompositeMetadataExtractor()
        for name in ("source", "title", "language", "stats"):
            try:
                composite.add(self.registry.get_extractor(name))
            except Exception:  # noqa: BLE001 - a missing optional extractor is not fatal
                continue
        return composite

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #

    def sources(self) -> list[KnowledgeSource]:
        return self.registry.sources()

    def source(self, source_id: str) -> KnowledgeSource:
        return self.registry.get_source(source_id)

    def indexer(self) -> KnowledgeIndexer:
        return self._indexer

    def collections(self) -> list[KnowledgeCollection]:
        return self._indexer.collections()

    def collection(self, collection_id: str) -> KnowledgeCollection | None:
        return self._indexer.collection(collection_id)

    # ------------------------------------------------------------------ #
    # Ingestion                                                          #
    # ------------------------------------------------------------------ #

    async def index_collection(self, collection_id: str) -> IndexResult:
        """Run the full pipeline for a configured collection.

        Returns an :class:`IndexResult` with the per-document
        :class:`KnowledgeVersion`\\ s. Incremental: documents whose checksum
        did not change are reported ``unchanged`` and not re-indexed.
        """
        collection_config = self._collection_config(collection_id)
        source = self.registry.get_source(collection_config.source)
        chunking = collection_config.chunking

        references = await self._list_references(source, collection_config)
        seen: set[str] = set()
        result = IndexResult(collection_id=collection_id, documents_seen=len(references))

        for reference in references:
            raw = await self._load_reference(source, reference)
            document = self._parse_document(raw, reference, source, collection_config)
            if collection_config.formats and document.format not in collection_config.formats:
                continue
            chunks = self._chunk_document(document, chunking)
            document.metadata = self._extractor.extract(document)
            document.language = document.language or str(document.metadata.get("language", ""))
            document.checksum = document.checksum or self._checksum(document)
            seen.add(document.id)

            version = self._indexer.ingest(document, chunks, collection_id=collection_id)
            self._tally(result, version)
            result.versions.append(version)

        for version in self._indexer.reconcile(seen, collection_id=collection_id):
            result.removed += 1
            result.versions.append(version)

        result.chunks_total = sum(
            len(self._indexer.chunks(document.id))
            for document in self._indexer.documents(collection_id)
        )
        return result

    async def index_all(self) -> list[IndexResult]:
        """Index every enabled collection."""
        results: list[IndexResult] = []
        for collection_config in self.config.collections:
            if not collection_config.enabled:
                continue
            results.append(await self.index_collection(collection_config.id))
        return results

    # ------------------------------------------------------------------ #
    # Pipeline steps                                                     #
    # ------------------------------------------------------------------ #

    def _collection_config(self, collection_id: str) -> KnowledgeCollectionConfig:
        for collection_config in self.config.collections:
            if collection_config.id == collection_id:
                return collection_config
        raise KnowledgeSourceError(f"Collection {collection_id!r} is not configured")

    async def _list_references(
        self, source: KnowledgeSource, collection_config: KnowledgeCollectionConfig
    ) -> list[str]:
        try:
            references = await source.list_documents_async()
        except NotImplementedError:
            references = source.list_documents()
        if collection_config.topics and source.source_type == "openwrt":
            allowed = set(collection_config.topics)
            references = [
                reference for reference in references if reference.split(":", 1)[-1] in allowed
            ]
        if collection_config.pattern and source.source_type == "filesystem":
            import fnmatch

            references = [r for r in references if fnmatch.fnmatch(r, collection_config.pattern)]
        return references

    async def _load_reference(self, source: KnowledgeSource, reference: str) -> bytes:
        if source.source_type in ("filesystem", "static"):
            return await self._asyncify(lambda: source.load(reference))
        loader = self._loader_for_source(source)
        return await self._asyncify(lambda: _load_sync_or_async(loader, reference))

    def _loader_for_source(self, source: KnowledgeSource) -> KnowledgeLoader:
        if source.source_type == "filesystem":
            try:
                return self.registry.get_loader("file")
            except Exception:  # noqa: BLE001
                return self.registry.get_loader("directory")
        if source.source_type == "static":
            return self.registry.get_loader("text")
        return self.registry.get_loader("http")

    async def _asyncify(self, operation: Any) -> bytes:
        import asyncio

        return await asyncio.to_thread(operation)

    def _parse_document(
        self,
        raw: bytes,
        reference: str,
        source: KnowledgeSource,
        collection_config: KnowledgeCollectionConfig,
    ) -> KnowledgeDocument:
        format = self._format_for(source, reference, collection_config)
        parser: KnowledgeParser = self.registry.get_parser(format)
        return parser.parse(raw, reference=reference, source=source.id)

    def _format_for(
        self,
        source: KnowledgeSource,
        reference: str,
        collection_config: KnowledgeCollectionConfig,
    ) -> str:
        if hasattr(source, "format_for"):
            return source.format_for(reference)  # type: ignore[attr-defined]
        suffix = Path(reference).suffix.lower().lstrip(".")
        return suffix or "txt"

    def _chunk_document(
        self, document: KnowledgeDocument, chunking: ChunkingConfig
    ) -> list[KnowledgeChunk]:
        strategy = self.registry.get_chunker(chunking.strategy)
        if hasattr(strategy, "chunk_size"):
            strategy.chunk_size = chunking.chunk_size  # type: ignore[attr-defined]
        if hasattr(strategy, "window_size"):
            strategy.window_size = chunking.chunk_size  # type: ignore[attr-defined]
        if hasattr(strategy, "overlap") and chunking.overlap is not None:
            strategy.overlap = chunking.overlap  # type: ignore[attr-defined]
        return strategy.chunk(document)

    @staticmethod
    def _checksum(document: KnowledgeDocument) -> str:
        from knowledge.checksum import document_checksum

        return document_checksum(document.text)

    @staticmethod
    def _tally(result: IndexResult, version: KnowledgeVersion) -> None:
        if version.change == "added":
            result.added += 1
        elif version.change == "updated":
            result.updated += 1
        elif version.change == "unchanged":
            result.unchanged += 1
        elif version.change == "duplicate":
            result.duplicates += 1

    # ------------------------------------------------------------------ #
    # Queries                                                            #
    # ------------------------------------------------------------------ #

    def documents(self, collection_id: str) -> list[KnowledgeDocument]:
        return self._indexer.documents(collection_id)

    def chunks(self, document_id: str) -> list[KnowledgeChunk]:
        return self._indexer.chunks(document_id)

    def find_duplicates(self, collection_id: str) -> dict[str, list[str]]:
        return self._indexer.find_duplicates(collection_id)

    def versions(self, collection_id: str) -> list[KnowledgeVersion]:
        return self._indexer.versions(collection_id)


__all__ = ["KnowledgeManager"]
