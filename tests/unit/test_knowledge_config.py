"""Configuration tests for the knowledge platform."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from knowledge.config import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_CHUNK_STRATEGY,
    ChunkingConfig,
    KnowledgeCollectionConfig,
    KnowledgePlatformConfig,
)


def test_defaults() -> None:
    chunking = ChunkingConfig()
    assert chunking.strategy == DEFAULT_CHUNK_STRATEGY
    assert chunking.chunk_size == DEFAULT_CHUNK_SIZE
    assert chunking.overlap is None


def test_chunking_rejects_unknown_strategy() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfig(strategy="bogus")


def test_chunking_size_at_least_one() -> None:
    assert ChunkingConfig(chunk_size=0).chunk_size == 1
    assert ChunkingConfig(chunk_size=-3).chunk_size == 1


def test_collection_defaults() -> None:
    config = KnowledgeCollectionConfig(id="c1", source="static")
    assert config.description == ""
    assert config.topics is None
    assert config.pattern is None
    assert config.formats is None
    assert config.enabled is True
    assert config.effective_chunking().strategy == "fixed"


def test_collection_effective_chunking() -> None:
    config = KnowledgeCollectionConfig(
        id="c1", source="static", chunking=ChunkingConfig(strategy="paragraph")
    )
    assert config.effective_chunking().strategy == "paragraph"


def test_platform_rejects_unknown_indexer() -> None:
    with pytest.raises(ValidationError):
        KnowledgePlatformConfig(indexer_type="bogus")


def test_platform_from_dict() -> None:
    config = KnowledgePlatformConfig.from_dict(
        {
            "indexer_type": "memory",
            "chunking": {"strategy": "sliding", "chunk_size": 400},
            "collections": [{"id": "wireguard", "source": "openwrt", "topics": ["wireguard"]}],
        }
    )
    assert config.indexer_type == "memory"
    assert config.chunking.strategy == "sliding"
    assert config.chunking.chunk_size == 400
    assert config.collections[0].topics == ["wireguard"]


def test_platform_from_yaml(tmp_path) -> None:
    path = tmp_path / "knowledge.yaml"
    path.write_text(
        "indexer_type: filesystem\n"
        "indexer_path: data/knowledge_index\n"
        "collections:\n"
        "  - id: uci\n"
        "    source: openwrt\n"
        "    topics: [uci]\n",
        encoding="utf-8",
    )
    config = KnowledgePlatformConfig.from_file(path)
    assert config.indexer_type == "filesystem"
    assert config.collections[0].id == "uci"


def test_platform_from_toml(tmp_path) -> None:
    path = tmp_path / "knowledge.toml"
    path.write_text(
        'indexer_type = "memory"\n\n[[collections]]\nid = "wiki"\nsource = "openwrt"\n',
        encoding="utf-8",
    )
    config = KnowledgePlatformConfig.from_file(path)
    assert config.collections[0].source == "openwrt"


def test_platform_from_unknown_ext(tmp_path) -> None:
    path = tmp_path / "knowledge.txt"
    path.write_text("indexer_type: memory", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported config format"):
        KnowledgePlatformConfig.from_file(path)


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        KnowledgeCollectionConfig(id="c1", source="static", bogus=1)
    with pytest.raises(ValidationError):
        KnowledgePlatformConfig(indexer_type="memory", bogus=1)
