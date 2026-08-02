"""SQLite backend specifics: persistence across instances, connection errors."""

from __future__ import annotations

from pathlib import Path

from tests.unit.vectorstore_helpers import make_store
from vectorstore.errors import VectorStoreConnectionError
from vectorstore.models import SearchRequest, VectorDocument, VectorMetadata


async def test_sqlite_persists_across_instances(tmp_path) -> None:
    first = make_store("sqlite", tmp_path)
    await first.create_collection(
        "docs",
        dimension=2,
        metadata=VectorMetadata(values={"owner": "me"}),
    )
    await first.add_documents(
        "docs",
        [
            VectorDocument(
                id="a", vector=[1.0, 0.0], text="one", metadata=VectorMetadata(values={"kind": "x"})
            )
        ],
    )

    second = make_store("sqlite", tmp_path)
    assert second.collection_info is not None
    info = await second.collection_info("docs")
    assert info is not None
    assert info.dimension == 2
    assert info.metadata.get("owner") == "me"
    assert info.document_count == 1
    docs = await second.get_documents("docs", ["a"])
    assert docs[0].text == "one"
    results = await second.search("docs", SearchRequest(query_vector=[1.0, 0.0]))
    assert results[0].id == "a"

    db_path = Path(tmp_path) / "store"
    assert db_path.exists()


async def test_sqlite_connection_error(tmp_path) -> None:
    store = make_store("sqlite", tmp_path)
    store._path = Path(tmp_path) / "nope" / "missing" / "x.db"

    def bad() -> None:
        store._init_schema()

    try:
        await store._run(bad)
        raise AssertionError("expected VectorStoreConnectionError")
    except VectorStoreConnectionError:
        pass
