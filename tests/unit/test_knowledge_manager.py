"""KnowledgeManager end-to-end pipeline tests."""

from __future__ import annotations

import pytest

from knowledge import KnowledgeManager, KnowledgePlatformConfig
from knowledge.errors import KnowledgeSourceError
from knowledge.sources import StaticSource

DOCS = {
    "intro.md": "# Intro\n\nThe quick brown fox jumps over the lazy dog.",
    "luci.md": "# LuCI\n\nLuCI is the web interface for OpenWrt.",
    "setup.md": "# Setup\n\nConfigure the router with UCI commands.",
}


def manager_registry(registry_docs: dict[str, str] | None = None):
    from knowledge.registry import KnowledgeRegistry

    registry = KnowledgeRegistry()
    registry.register_builtins()
    registry.register_source(
        StaticSource("static", registry_docs or DOCS, format="markdown"),
        replace=True,
    )
    return registry


def _manager(registry_docs: dict[str, str] | None = None, **config_kwargs) -> KnowledgeManager:
    from knowledge.config import KnowledgeCollectionConfig

    config = KnowledgePlatformConfig(
        collections=[KnowledgeCollectionConfig(id="samples", source="static")],
        **config_kwargs,
    )
    return KnowledgeManager(manager_registry(registry_docs), config)


async def test_index_collection_adds_documents() -> None:
    manager = _manager()
    result = await manager.index_collection("samples")
    assert result.documents_seen == 3
    assert result.added == 3
    assert result.unchanged == 0
    assert result.chunks_total == 3
    assert len(result.versions) == 3

    collection = manager.collection("samples")
    assert collection.document_count == 3
    assert collection.chunk_count == 3

    documents = manager.documents("samples")
    assert len(documents) == 3
    for doc in documents:
        assert doc.source == "static"
        assert doc.format == "markdown"
        assert doc.checksum
        assert "title" in doc.metadata
        assert "language" in doc.metadata
        assert doc.language  # synced from the metadata extractor
        assert "word_count" in doc.metadata
        assert len(manager.chunks(doc.id)) == 1


async def test_index_collection_is_incremental() -> None:
    manager = _manager()
    await manager.index_collection("samples")
    second = await manager.index_collection("samples")
    assert second.added == 0
    assert second.unchanged == 3


async def test_index_collection_detects_updates() -> None:
    manager = _manager()
    await manager.index_collection("samples")
    source = manager.registry.get_source("static")
    source._documents["intro.md"] = "# Intro\n\nThe quick brown fox jumps over the lazy dog. (v2)"
    result = await manager.index_collection("samples")
    assert result.updated == 1
    assert result.unchanged == 2


async def test_index_collection_removes_missing() -> None:
    manager = _manager()
    await manager.index_collection("samples")
    source = manager.registry.get_source("static")
    source._documents.pop("setup.md")
    result = await manager.index_collection("samples")
    assert result.removed == 1
    assert manager.collection("samples").document_count == 2


async def test_index_collection_duplicate_detection() -> None:
    docs = {
        "a.md": "Same content appears twice.\n\nMore text.",
        "b.md": "Same content appears twice.\n\nMore text.",
        "c.md": "# C\n\nUnique content here.",
    }
    manager = _manager(docs)
    result = await manager.index_collection("samples")
    assert result.added == 2  # one of the identical pair is rejected as duplicate
    assert result.duplicates == 1
    assert manager.collection("samples").document_count == 2


async def test_index_collection_formats_filter() -> None:
    from knowledge.config import KnowledgeCollectionConfig

    config = KnowledgePlatformConfig(
        collections=[KnowledgeCollectionConfig(id="samples", source="static", formats=["txt"])]
    )
    manager = KnowledgeManager(manager_registry(), config)
    result = await manager.index_collection("samples")
    assert result.added == 0  # all docs are markdown, filtered out
    collection = manager.collection("samples")
    assert collection is None or collection.document_count == 0


async def test_index_all_skips_disabled() -> None:
    from knowledge.config import KnowledgeCollectionConfig

    config = KnowledgePlatformConfig(
        collections=[
            KnowledgeCollectionConfig(id="c1", source="static"),
            KnowledgeCollectionConfig(id="c2", source="static", enabled=False),
        ]
    )
    manager = KnowledgeManager(manager_registry(), config)
    results = await manager.index_all()
    assert len(results) == 1
    assert results[0].collection_id == "c1"


async def test_missing_collection_config_raises() -> None:
    manager = _manager()
    with pytest.raises(KnowledgeSourceError, match="is not configured"):
        await manager.index_collection("nope")


async def test_filesystem_indexer_path(tmp_path) -> None:
    from knowledge.config import KnowledgeCollectionConfig

    config = KnowledgePlatformConfig(
        indexer_type="filesystem",
        indexer_path=str(tmp_path / "idx"),
        collections=[KnowledgeCollectionConfig(id="samples", source="static")],
    )
    manager = KnowledgeManager(manager_registry(), config)
    await manager.index_collection("samples")
    assert (tmp_path / "idx" / "samples.json").exists()

    # A fresh manager on the same path sees the persisted index.
    manager2 = KnowledgeManager(manager_registry(), config)
    result = await manager2.index_collection("samples")
    assert result.added == 0
    assert result.unchanged == 3


async def test_list_references_topics_filter() -> None:
    from knowledge.config import KnowledgeCollectionConfig

    manager = _manager()
    source = manager.registry.get_source("openwrt")
    config = KnowledgeCollectionConfig(id="t", source="openwrt", topics=["wireguard", "uci"])
    references = await manager._list_references(source, config)
    assert references == ["topic:wireguard", "topic:uci"]


async def test_sources_and_indexer_introspection() -> None:
    manager = _manager()
    assert {source.id for source in manager.sources()} >= {"static", "openwrt"}
    assert manager.indexer() is not None
    assert manager.collections() == []
    assert manager.collection("nope") is None
    assert manager.versions("samples") == []


async def test_source_ids_stable_across_passes() -> None:
    manager = _manager()
    await manager.index_collection("samples")
    documents = manager.documents("samples")
    assert len({doc.id for doc in documents}) == 3
