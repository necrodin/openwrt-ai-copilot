"""FAISS backend specifics: lazy dependency guard, persistence."""

from __future__ import annotations

import pytest

from tests.unit.vectorstore_helpers import make_store
from vectorstore.backends import faiss as faiss_module
from vectorstore.config import VectorStoreConfig
from vectorstore.errors import VectorStoreError
from vectorstore.models import VectorDocument


@pytest.fixture(autouse=True)
def _restore_faiss():
    """Ensure the real faiss import is restored after the guard test."""
    yield


def test_faiss_missing_dependency_raises(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(faiss_module, "faiss", None)
    with pytest.raises(VectorStoreError):
        faiss_module.FAISSVectorStore(VectorStoreConfig(type="faiss", path=str(tmp_path / "faiss")))


async def test_faiss_persists_across_instances(tmp_path) -> None:
    first = make_store("faiss", tmp_path)
    await first.create_collection("docs", dimension=2)
    await first.add_documents(
        "docs",
        [
            VectorDocument(id="a", vector=[1.0, 0.0], text="one"),
            VectorDocument(id="b", vector=[0.0, 1.0], text="two"),
        ],
    )

    second = make_store("faiss", tmp_path)
    info = await second.collection_info("docs")
    assert info is not None
    assert info.document_count == 2
    docs = await second.get_documents("docs", ["b"])
    assert docs[0].text == "two"

    from vectorstore.models import SearchRequest

    results = await second.search("docs", SearchRequest(query_vector=[1.0, 0.0]))
    assert results[0].id == "a"


async def test_faiss_rebuild_after_update_and_delete(tmp_path) -> None:
    store = make_store("faiss", tmp_path)
    await store.create_collection("docs", dimension=2)
    await store.add_documents(
        "docs",
        [
            VectorDocument(id="a", vector=[1.0, 0.0], text="one"),
            VectorDocument(id="b", vector=[0.0, 1.0], text="two"),
        ],
    )
    await store.delete_documents("docs", ["a"])
    await store.update_documents("docs", [VectorDocument(id="b", vector=[1.0, 0.0], text="two v2")])

    from vectorstore.models import SearchRequest

    results = await store.search("docs", SearchRequest(query_vector=[1.0, 0.0], top_k=5))
    assert [r.id for r in results] == ["b"]
    assert results[0].text == "two v2"
