"""Registry tests for the knowledge platform."""

from __future__ import annotations

import pytest

from knowledge.errors import UnsupportedFormatError
from knowledge.models import KnowledgeDocument
from knowledge.registry import KnowledgeRegistry, KnowledgeRegistryError
from knowledge.sources import StaticSource


def _static(source_id: str = "static") -> StaticSource:
    return StaticSource(source_id)


def test_register_and_get_source() -> None:
    registry = KnowledgeRegistry()
    registry.register_source(_static("my-source"))
    assert registry.get_source("my-source").id == "my-source"


def test_duplicate_source_raises() -> None:
    registry = KnowledgeRegistry()
    registry.register_source(_static())
    with pytest.raises(KnowledgeRegistryError, match="already registered"):
        registry.register_source(_static())


def test_replace_source() -> None:
    registry = KnowledgeRegistry()
    registry.register_source(_static("a"))
    registry.register_source(_static("a"), replace=True)
    assert registry.get_source("a").id == "a"


def test_missing_source_raises() -> None:
    with pytest.raises(KnowledgeRegistryError, match="is not registered"):
        KnowledgeRegistry().get_source("nope")


def test_register_builtins_is_idempotent_and_preserves_user() -> None:
    registry = KnowledgeRegistry()
    user = _static("custom-static")
    registry.register_source(user)
    registry.register_builtins()
    registry.register_builtins()  # idempotent, must not raise
    assert registry.get_source("custom-static") is user
    assert registry.get_source("openwrt") is not None
    assert registry.get_source("static") is not None


def test_builtins_registered() -> None:
    registry = KnowledgeRegistry()
    registry.register_builtins()
    assert registry.parsers() == ["html", "json", "markdown", "pdf", "txt", "xml", "yaml"]
    assert set(registry.chunkers()) == {"fixed", "heading", "paragraph", "sliding"}
    assert set(registry.extractors()) == {"headings", "language", "source", "stats", "title"}
    assert set(registry.indexers()) == {"filesystem", "memory"}
    assert set(registry.loaders()) == {"directory", "file", "text"}


def test_get_parser_missing_raises_unsupported() -> None:
    registry = KnowledgeRegistry()
    registry.register_builtins()
    with pytest.raises(UnsupportedFormatError, match="No knowledge parser"):
        registry.get_parser("docx")


def test_get_parser_is_case_insensitive() -> None:
    registry = KnowledgeRegistry()
    registry.register_builtins()
    assert registry.get_parser("MARKDOWN").format == "markdown"


def test_get_loader_missing_raises() -> None:
    with pytest.raises(KnowledgeRegistryError, match="is not registered"):
        KnowledgeRegistry().get_loader("nope")


def test_register_loader_with_override_type() -> None:
    registry = KnowledgeRegistry()

    class _Loader:
        loader_type = "base"

        def load(self, reference: str) -> bytes:
            return b""

    registry.register_loader(_Loader(), loader_type="aliased")
    assert registry.loaders() == ["aliased"]
    assert registry.get_loader("aliased").loader_type == "base"


def test_clear() -> None:
    registry = KnowledgeRegistry()
    registry.register_builtins()
    registry.clear()
    assert registry.sources() == []
    assert registry.parsers() == []


def test_unregister_source() -> None:
    registry = KnowledgeRegistry()
    registry.register_source(_static("x"))
    registry.unregister_source("x")
    assert registry.sources() == []


def test_chunker_and_extractor_and_indexer_registration() -> None:
    registry = KnowledgeRegistry()

    class _Chunker:
        strategy_type = "mine"

        def chunk(self, document: KnowledgeDocument) -> list:
            return []

    class _Extractor:
        extractor_type = "mine"

        def extract(self, document: KnowledgeDocument):
            from knowledge.models import KnowledgeMetadata

            return KnowledgeMetadata()

    class _Indexer:
        indexer_type = "mine"

    registry.register_chunker(_Chunker())
    registry.register_extractor(_Extractor())
    registry.register_indexer(_Indexer())
    assert registry.get_chunker("mine").strategy_type == "mine"
    assert registry.get_extractor("mine").extractor_type == "mine"
    assert registry.get_indexer("mine").indexer_type == "mine"
    assert registry.chunkers() == ["mine"]
    assert registry.extractors() == ["mine"]
    assert registry.indexers() == ["mine"]
