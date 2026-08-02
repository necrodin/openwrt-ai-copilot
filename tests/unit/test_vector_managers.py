"""Manager facade tests — everything routes to the underlying store with the
correct namespace defaulting."""

from __future__ import annotations

import pytest

from tests.unit.vectorstore_helpers import make_store
from vectorstore.managers import (
    CollectionManager,
    DocumentManager,
    MetadataManager,
)
from vectorstore.models import (
    MetadataFilter,
    VectorDocument,
    VectorMetadata,
)


@pytest.fixture
def managers(tmp_path):
    store = make_store("sqlite", tmp_path)
    return (
        CollectionManager(store),
        DocumentManager(store),
        MetadataManager(store),
    )


async def test_collection_manager_roundtrip(managers) -> None:
    collections, documents, _ = managers
    info = await collections.create("docs", dimension=3)
    assert info.name == "docs"
    assert info.namespace == "default"

    assert await collections.info("docs") is not None
    assert await collections.info("missing") is None
    assert len(await collections.list()) == 1

    await documents.add("docs", [VectorDocument(id="a", vector=[1.0, 0.0, 0.0], text="hi")])
    assert (await collections.stats("docs")).document_count == 1

    await collections.delete("docs")
    assert len(await collections.list()) == 0


async def test_document_manager_search_builds_request(managers) -> None:
    collections, documents, _ = managers
    await collections.create("docs", dimension=3)
    await documents.add(
        "docs",
        [
            VectorDocument(
                id="a",
                vector=[1.0, 0.0, 0.0],
                text="apple",
                metadata=VectorMetadata(values={"kind": "fruit"}),
            ),
            VectorDocument(
                id="b",
                vector=[0.0, 1.0, 0.0],
                text="broccoli",
                metadata=VectorMetadata(values={"kind": "veg"}),
            ),
        ],
    )
    results = await documents.search(
        "docs", [1.0, 0.0, 0.0], top_k=5, filters=[MetadataFilter(field="kind", value="fruit")]
    )
    assert [r.id for r in results] == ["a"]

    assert (await documents.get("docs", ["b"]))[0].text == "broccoli"
    assert await documents.delete("docs", ["a"]) == 1
    assert (
        await documents.update(
            "docs", [VectorDocument(id="b", vector=[0.0, 1.0, 0.0], text="broccoli v2")]
        )
        == 1
    )


async def test_metadata_manager_merge_and_replace(managers) -> None:
    collections, documents, metadata = managers
    await collections.create("docs", dimension=3)
    await documents.add("docs", [VectorDocument(id="a", vector=[1.0, 0.0, 0.0], text="hi")])

    await metadata.set("docs", "a", VectorMetadata(values={"extra": "yes"}))
    assert (await metadata.get("docs", "a")).to_dict() == {"extra": "yes"}

    await metadata.set("docs", "a", VectorMetadata(values={"kind": "x"}), merge=True)
    assert (await metadata.get("docs", "a")).to_dict() == {"extra": "yes", "kind": "x"}

    await metadata.set("docs", "a", VectorMetadata(values={"only": "z"}), merge=False)
    assert (await metadata.get("docs", "a")).to_dict() == {"only": "z"}

    matched = await metadata.filter("docs", [MetadataFilter(field="only", value="z")])
    assert [doc.id for doc in matched] == ["a"]
