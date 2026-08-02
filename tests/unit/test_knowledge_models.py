"""Data model tests for the knowledge platform."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from knowledge.models import (
    IndexResult,
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeMetadata,
    KnowledgeVersion,
)


def test_metadata_helpers() -> None:
    metadata = KnowledgeMetadata(values={"topic": "wireguard", "level": 2})
    assert metadata.get("topic") == "wireguard"
    assert metadata.get("missing", "fallback") == "fallback"
    assert metadata["level"] == 2
    assert metadata.to_dict() == {"topic": "wireguard", "level": 2}
    assert "topic" in metadata
    assert len(metadata) == 2
    assert bool(metadata) is True
    assert bool(KnowledgeMetadata()) is False


def test_metadata_merge_overlays() -> None:
    base = KnowledgeMetadata(values={"a": 1, "b": 2})
    overlay = KnowledgeMetadata(values={"b": 3, "c": 4})
    merged = base.merge(overlay)
    assert merged.to_dict() == {"a": 1, "b": 3, "c": 4}
    assert base.to_dict() == {"a": 1, "b": 2}


def test_document_defaults() -> None:
    doc = KnowledgeDocument(id="d1")
    assert doc.source == ""
    assert doc.format == ""
    assert doc.text == ""
    assert doc.language == ""
    assert doc.metadata.values == {}
    assert doc.checksum == ""
    assert doc.version == 1
    assert doc.created_at is None
    assert doc.text_length == 0


def test_document_text_length() -> None:
    doc = KnowledgeDocument(id="d1", text="hello world")
    assert doc.text_length == 11


def test_chunk_defaults() -> None:
    chunk = KnowledgeChunk(id="d1#0", document_id="d1", index=0, text="t")
    assert chunk.heading == ""
    assert chunk.metadata.values == {}
    assert chunk.checksum == ""


def test_chunk_checksum_filled_by_chunker() -> None:
    from knowledge.chunking import FixedSizeChunkStrategy

    doc = KnowledgeDocument(id="d1", text="alpha beta gamma")
    chunk = FixedSizeChunkStrategy(chunk_size=2).chunk(doc)[0]
    assert chunk.id == "d1#0"
    assert chunk.checksum


def test_collection_counters() -> None:
    collection = KnowledgeCollection(id="c1", name="WireGuard")
    assert collection.document_count == 0
    collection.document_ids = ["a", "b", "c"]
    assert collection.document_count == 3
    collection.chunk_count = 10
    assert collection.updated_at is None


def test_version_required_fields() -> None:
    version = KnowledgeVersion(document_id="d1", version=2, checksum="abc", change="updated")
    assert version.source == ""
    assert version.indexed_at is None


def test_version_rejects_bad_change() -> None:
    with pytest.raises(ValidationError):
        KnowledgeVersion(document_id="d1", version=1, checksum="x", change="bogus")


def test_index_result_changed() -> None:
    result = IndexResult(collection_id="c1")
    assert result.changed is False
    result.added = 1
    assert result.changed is True


def test_index_result_counts_default_to_zero() -> None:
    result = IndexResult(collection_id="c1", documents_seen=4)
    assert result.added == 0
    assert result.updated == 0
    assert result.unchanged == 0
    assert result.removed == 0
    assert result.duplicates == 0
    assert result.chunks_total == 0
    assert result.versions == []


def test_models_roundtrip_json() -> None:
    doc = KnowledgeDocument(
        id="d1",
        source="s",
        text="hello",
        metadata=KnowledgeMetadata(values={"x": 1}),
        created_at=datetime.now(UTC),
    )
    data = doc.model_dump(mode="json")
    restored = KnowledgeDocument.model_validate(data)
    assert restored == doc
