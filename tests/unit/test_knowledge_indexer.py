"""Indexer tests for the knowledge platform (memory + filesystem)."""

from __future__ import annotations

import pytest

from knowledge.errors import KnowledgeIndexError
from knowledge.indexer import FileSystemKnowledgeIndexer, InMemoryKnowledgeIndexer
from knowledge.models import KnowledgeDocument


def _doc(document_id: str, text: str, source: str = "static") -> KnowledgeDocument:
    from knowledge.checksum import document_checksum

    return KnowledgeDocument(
        id=document_id,
        source=source,
        reference=f"ref:{document_id}",
        format="markdown",
        text=text,
        checksum=document_checksum(text),
    )


def _chunks(document: KnowledgeDocument) -> list:
    from knowledge.chunking import FixedSizeChunkStrategy

    return FixedSizeChunkStrategy(chunk_size=100).chunk(document)


@pytest.fixture(params=[InMemoryKnowledgeIndexer, "filesystem"])
def indexer(request, tmp_path):
    if request.param == "filesystem":
        yield FileSystemKnowledgeIndexer(tmp_path / "index")
    else:
        yield InMemoryKnowledgeIndexer()


def test_ingest_adds_document_and_chunks(indexer) -> None:
    doc = _doc("d1", "alpha beta gamma")
    version = indexer.ingest(doc, _chunks(doc), collection_id="c1")
    assert version.change == "added"
    assert version.version == 1
    assert indexer.exists("d1")
    assert indexer.get_document("d1").text == doc.text
    assert len(indexer.chunks("d1")) == 1
    assert indexer.chunks("d1")[0].document_id == "d1"
    assert indexer.documents("c1")[0].id == "d1"
    assert indexer.collection("c1").document_count == 1


def test_ingest_unchanged_when_checksum_same(indexer) -> None:
    indexer.ingest(_doc("d1", "same text"), _chunks(_doc("d1", "same text")), collection_id="c1")
    version = indexer.ingest(
        _doc("d1", "same text"), _chunks(_doc("d1", "same text")), collection_id="c1"
    )
    assert version.change == "unchanged"
    assert version.version == 1
    assert len(indexer.versions("c1")) == 1  # unchanged is not recorded


def test_ingest_updates_version_on_change(indexer) -> None:
    indexer.ingest(
        _doc("d1", "version one"), _chunks(_doc("d1", "version one")), collection_id="c1"
    )
    version = indexer.ingest(
        _doc("d1", "version two"), _chunks(_doc("d1", "version two")), collection_id="c1"
    )
    assert version.change == "updated"
    assert version.version == 2
    assert indexer.get_document("d1").version == 2
    changes = [v.change for v in indexer.versions("c1")]
    assert changes == ["added", "updated"]


def test_ingest_duplicate_across_ids(indexer) -> None:
    indexer.ingest(
        _doc("d1", "dup content"), _chunks(_doc("d1", "dup content")), collection_id="c1"
    )
    version = indexer.ingest(
        _doc("d2", "dup content"), _chunks(_doc("d2", "dup content")), collection_id="c1"
    )
    assert version.change == "duplicate"
    assert version.version == 1
    assert indexer.exists("d2") is False  # duplicate is not stored


def test_find_duplicates_groups(indexer) -> None:
    indexer.ingest(
        _doc("d1", "shared text"), _chunks(_doc("d1", "shared text")), collection_id="c1"
    )
    indexer.ingest(
        _doc("d2", "shared text"), _chunks(_doc("d2", "shared text")), collection_id="c1"
    )
    indexer.ingest(
        _doc("d3", "unique text"), _chunks(_doc("d3", "unique text")), collection_id="c1"
    )
    duplicates = indexer.find_duplicates("c1")
    assert len(duplicates) == 0  # d2 was rejected, so no group has 2 stored docs


def test_reconcile_removes_missing(indexer) -> None:
    indexer.ingest(_doc("d1", "a"), _chunks(_doc("d1", "a")), collection_id="c1")
    indexer.ingest(_doc("d2", "b"), _chunks(_doc("d2", "b")), collection_id="c1")
    removed = indexer.reconcile({"d1"}, collection_id="c1")
    assert [v.change for v in removed] == ["removed"]
    assert removed[0].document_id == "d2"
    assert indexer.exists("d2") is False
    assert indexer.collection("c1").document_count == 1


def test_collections_listing(indexer) -> None:
    indexer.ingest(_doc("d1", "a"), _chunks(_doc("d1", "a")), collection_id="c1")
    indexer.ingest(_doc("d2", "b"), _chunks(_doc("d2", "b")), collection_id="c2")
    assert [c.id for c in indexer.collections()] == ["c1", "c2"]
    assert indexer.collection("missing") is None


def test_versions_tracking(indexer) -> None:
    indexer.ingest(_doc("d1", "v1"), _chunks(_doc("d1", "v1")), collection_id="c1")
    indexer.ingest(_doc("d1", "v2"), _chunks(_doc("d1", "v2")), collection_id="c1")
    versions = indexer.versions("c1")
    assert [v.change for v in versions] == ["added", "updated"]
    assert versions[1].version == 2


def test_in_memory_flush_is_noop() -> None:
    assert InMemoryKnowledgeIndexer().flush() is None


def test_filesystem_persists_across_instances(tmp_path) -> None:
    root = tmp_path / "idx"
    first = FileSystemKnowledgeIndexer(root)
    first.ingest(_doc("d1", "persist me"), _chunks(_doc("d1", "persist me")), collection_id="c1")
    first.ingest(
        _doc("d1", "persist me v2"), _chunks(_doc("d1", "persist me v2")), collection_id="c1"
    )

    second = FileSystemKnowledgeIndexer(root)
    assert second.exists("d1")
    assert second.get_document("d1").version == 2
    assert second.get_document("d1").text == "persist me v2"
    assert [v.change for v in second.versions("c1")] == ["added", "updated"]
    assert second.collection("c1").document_count == 1


def test_filesystem_cross_instance_unchanged(tmp_path) -> None:
    root = tmp_path / "idx"
    first = FileSystemKnowledgeIndexer(root)
    first.ingest(_doc("d1", "same"), _chunks(_doc("d1", "same")), collection_id="c1")
    second = FileSystemKnowledgeIndexer(root)
    version = second.ingest(_doc("d1", "same"), _chunks(_doc("d1", "same")), collection_id="c1")
    assert version.change == "unchanged"
    assert version.version == 1


def test_filesystem_empty_root_is_memory() -> None:
    indexer = FileSystemKnowledgeIndexer("")
    indexer.ingest(_doc("d1", "x"), _chunks(_doc("d1", "x")), collection_id="c1")
    assert indexer.get_document("d1") is not None
    indexer.flush()  # no-op, must not raise


def test_filesystem_corrupt_state_raises(tmp_path) -> None:
    root = tmp_path / "idx"
    root.mkdir()
    (root / "c1.json").write_text("{not valid json", encoding="utf-8")
    with pytest.raises(KnowledgeIndexError):
        FileSystemKnowledgeIndexer(root)


def test_chunk_count_totals_across_documents(indexer) -> None:
    contents = ["word " * 50, "alpha " * 50, "beta " * 50]
    for i, content in enumerate(contents):
        indexer.ingest(_doc(f"d{i}", content), _chunks(_doc(f"d{i}", content)), collection_id="c1")
    assert indexer.collection("c1").chunk_count == 3
