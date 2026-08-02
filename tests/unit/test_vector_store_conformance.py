"""Conformance suite: every in-process backend must behave identically.

Runs the full behavioural contract against the SQLite (reference) and FAISS
backends. The HTTP backends (Qdrant, Chroma) are covered by protocol-level
tests in ``test_vector_qdrant.py`` / ``test_vector_chroma.py``.

These tests double as the specification for what "the same API" means:
collections, documents, batch insert, search, metadata filters, namespaces,
pagination, and versioning.
"""

from __future__ import annotations

import pytest

from tests.unit.vectorstore_helpers import make_store
from vectorstore.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
    DocumentNotFoundError,
    VectorStoreError,
)
from vectorstore.models import (
    MetadataFilter,
    SearchRequest,
    VectorDocument,
    VectorMetadata,
)

IN_PROCESS_BACKENDS = ["sqlite", "faiss"]


@pytest.fixture(params=IN_PROCESS_BACKENDS)
def store(request, tmp_path):
    return make_store(request.param, tmp_path)


def _documents() -> list[VectorDocument]:
    return [
        VectorDocument(
            id="a",
            vector=[1.0, 0.0, 0.0, 0.0],
            text="alpha",
            metadata=VectorMetadata(values={"kind": "fruit", "size": 3}),
        ),
        VectorDocument(
            id="b",
            vector=[0.0, 1.0, 0.0, 0.0],
            text="beta",
            metadata=VectorMetadata(values={"kind": "vegetable", "size": 7}),
        ),
        VectorDocument(
            id="c",
            vector=[0.9, 0.1, 0.0, 0.0],
            text="gamma",
            metadata=VectorMetadata(values={"kind": "fruit", "size": 1}),
        ),
    ]


async def test_collection_lifecycle(store) -> None:
    info = await store.create_collection("docs", dimension=4)
    assert info.name == "docs"
    assert info.dimension == 4
    assert info.document_count == 0

    listed = await store.list_collections()
    assert [item.name for item in listed] == ["docs"]
    assert await store.collection_info("docs") is not None
    assert await store.collection_info("missing") is None

    stats = await store.stats("docs")
    assert stats.document_count == 0
    assert stats.dimension == 4

    await store.delete_collection("docs")
    assert await store.collection_info("docs") is None
    with pytest.raises(CollectionNotFoundError):
        await store.delete_collection("docs")


async def test_create_duplicate_raises(store) -> None:
    await store.create_collection("docs", dimension=4)
    with pytest.raises(CollectionExistsError):
        await store.create_collection("docs", dimension=4)


async def test_batch_add_and_get(store) -> None:
    await store.create_collection("docs", dimension=4)
    ids = await store.add_documents("docs", _documents())
    assert ids == ["a", "b", "c"]

    fetched = await store.get_documents("docs", ["b", "a", "zz"])
    assert [doc.id for doc in fetched] == ["b", "a"]
    assert fetched[0].text == "beta"
    assert fetched[0].metadata.get("kind") == "vegetable"

    assert (await store.stats("docs")).document_count == 3


async def test_add_duplicate_id_raises(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())
    with pytest.raises(VectorStoreError):
        await store.add_documents("docs", [_documents()[0]])


async def test_update_upserts_and_bumps_version(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())

    count = await store.update_documents(
        "docs",
        [
            VectorDocument(
                id="a",
                vector=[0.0, 1.0, 0.0, 0.0],
                text="alpha v2",
                metadata=VectorMetadata(values={"kind": "fruit", "size": 3}),
            ),
            VectorDocument(id="d", vector=[0.0, 0.0, 1.0, 0.0], text="delta"),
        ],
    )
    assert count == 2

    fetched = await store.get_documents("docs", ["a", "d"])
    assert fetched[0].version == 2
    assert fetched[0].text == "alpha v2"
    assert fetched[1].version == 1

    stats = await store.stats("docs")
    assert stats.document_count == 4
    assert stats.max_version == 2


async def test_delete_documents_returns_count(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())
    assert await store.delete_documents("docs", ["a", "zz"]) == 1
    assert [doc.id for doc in await store.get_documents("docs", ["a", "b"])] == ["b"]


async def test_search_ranks_by_cosine(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())

    results = await store.search("docs", SearchRequest(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=3))
    assert [result.id for result in results] == ["a", "c", "b"]
    assert results[0].score > results[1].score > results[2].score
    assert results[0].text == "alpha"


async def test_search_respects_metadata_filters(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())

    results = await store.search(
        "docs",
        SearchRequest(
            query_vector=[1.0, 0.0, 0.0, 0.0],
            top_k=10,
            filters=[MetadataFilter(field="kind", op="eq", value="fruit")],
        ),
    )
    assert {result.id for result in results} == {"a", "c"}


async def test_search_pagination(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())

    page = await store.search(
        "docs",
        SearchRequest(query_vector=[1.0, 0.0, 0.0, 0.0], top_k=10, offset=1, limit=1),
    )
    assert [result.id for result in page] == ["c"]


async def test_search_dimension_mismatch(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())
    with pytest.raises(DimensionMismatchError):
        await store.search("docs", SearchRequest(query_vector=[1.0, 0.0, 0.0]))


async def test_add_dimension_mismatch(store) -> None:
    await store.create_collection("docs", dimension=4)
    with pytest.raises(DimensionMismatchError):
        await store.add_documents("docs", [VectorDocument(id="x", vector=[1.0, 0.0])])


async def test_filter_documents_by_metadata(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())

    matched = await store.filter_documents(
        "docs",
        [MetadataFilter(field="size", op="gte", value=2)],
    )
    assert {doc.id for doc in matched} == {"a", "b"}

    page = await store.filter_documents(
        "docs", [MetadataFilter(field="kind", op="eq", value="fruit")], offset=1
    )
    assert [doc.id for doc in page] == ["c"]


async def test_metadata_set_get_merge(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())

    meta = await store.get_metadata("docs", "a")
    assert meta.get("kind") == "fruit"

    await store.set_metadata(
        "docs",
        "a",
        VectorMetadata(values={"extra": "yes"}),
    )
    assert (await store.get_metadata("docs", "a")).get("extra") == "yes"

    with pytest.raises(DocumentNotFoundError):
        await store.get_metadata("docs", "nope")


async def test_namespaces_are_isolated(store) -> None:
    await store.create_collection("docs", dimension=4, namespace="ns1")
    await store.create_collection("docs", dimension=4, namespace="ns2")
    await store.add_documents("docs", _documents(), namespace="ns1")

    assert len(await store.list_collections(namespace="ns1")) == 1
    assert len(await store.list_collections(namespace="ns2")) == 1
    assert len(await store.list_collections()) == 2
    assert (await store.stats("docs", namespace="ns1")).document_count == 3
    assert (await store.stats("docs", namespace="ns2")).document_count == 0


async def test_default_namespace(store) -> None:
    await store.create_collection("docs", dimension=4)
    await store.add_documents("docs", _documents())
    assert len(await store.list_collections(namespace="default")) == 1


async def test_missing_collection_operations_raise(store) -> None:
    with pytest.raises(CollectionNotFoundError):
        await store.add_documents("docs", _documents())
    with pytest.raises(CollectionNotFoundError):
        await store.get_documents("docs", ["a"])
    with pytest.raises(CollectionNotFoundError):
        await store.search("docs", SearchRequest(query_vector=[1.0, 0.0, 0.0, 0.0]))
    with pytest.raises(CollectionNotFoundError):
        await store.stats("docs")


async def test_health_is_true(store) -> None:
    assert await store.health() is True
