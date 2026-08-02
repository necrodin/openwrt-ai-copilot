"""Chroma backend tests using a stateful ``httpx.MockTransport``.

The mock emulates the Chroma REST API subset the adapter uses, so the tests
prove the adapter's request/response mapping without touching the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

import httpx
import pytest

from tests.unit.vectorstore_helpers import make_http_store
from vectorstore.backends._math import cosine_similarity
from vectorstore.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
    VectorStoreConnectionError,
)
from vectorstore.models import (
    SearchRequest,
    VectorDocument,
    VectorMetadata,
)


@dataclass
class ChromaState:
    collections: dict = field(default_factory=dict)
    seq: int = 0


def make_chroma_handler(state: ChromaState):
    async def handler(request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path
        parts = [p for p in path.split("/") if p]
        is_collections_root = (
            parts[:5] == ["api", "v1", "tenants", "default", "databases"]
            and parts[-1] == "collections"
        )
        if method == "GET" and is_collections_root:
            name = request.url.params.get("name")
            items = []
            for cid, entry in state.collections.items():
                if name is not None and entry["name"] != name:
                    continue
                items.append(
                    {
                        "id": cid,
                        "name": entry["name"],
                        "metadata": entry["metadata"],
                    }
                )
            return httpx.Response(200, json=items)
        if method == "POST" and is_collections_root:
            body = json.loads(request.content)
            for _, entry in state.collections.items():
                if entry["name"] == body["name"]:
                    return httpx.Response(409, json={"error": "exists"})
            state.seq += 1
            cid = f"col-{state.seq}"
            state.collections[cid] = {
                "name": body["name"],
                "metadata": body.get("metadata", {}),
                "records": {"ids": [], "embeddings": [], "documents": [], "metadatas": []},
            }
            return httpx.Response(200, json={"id": cid, "name": body["name"]})
        if len(parts) >= 4 and parts[:3] == ["api", "v1", "collections"]:
            cid = parts[3]
            entry = state.collections.get(cid)
            if entry is None:
                return httpx.Response(404, json={"error": "not found"})
            records = entry["records"]
            if method == "DELETE" and len(parts) == 4:
                state.collections.pop(cid, None)
                return httpx.Response(200, json=True)
            if method == "GET" and len(parts) == 5 and parts[4] == "count":
                return httpx.Response(200, json=len(records["ids"]))
            if method == "POST" and len(parts) == 5:
                action = parts[4]
                body = json.loads(request.content)
                if action == "add":
                    for index, record_id in enumerate(body["ids"]):
                        records["ids"].append(record_id)
                        records["embeddings"].append(body["embeddings"][index])
                        records["documents"].append(body["documents"][index])
                        records["metadatas"].append(body["metadatas"][index])
                    return httpx.Response(200, json=True)
                if action == "upsert":
                    for index, record_id in enumerate(body["ids"]):
                        if record_id in records["ids"]:
                            pos = records["ids"].index(record_id)
                            records["embeddings"][pos] = body["embeddings"][index]
                            records["documents"][pos] = body["documents"][index]
                            records["metadatas"][pos] = body["metadatas"][index]
                        else:
                            records["ids"].append(record_id)
                            records["embeddings"].append(body["embeddings"][index])
                            records["documents"].append(body["documents"][index])
                            records["metadatas"].append(body["metadatas"][index])
                    return httpx.Response(200, json=True)
                if action == "update":
                    for index, record_id in enumerate(body["ids"]):
                        if record_id in records["ids"]:
                            pos = records["ids"].index(record_id)
                            records["embeddings"][pos] = body["embeddings"][index]
                            records["documents"][pos] = body["documents"][index]
                            records["metadatas"][pos] = body["metadatas"][index]
                    return httpx.Response(200, json=True)
                if action == "delete":
                    for record_id in body.get("ids", []):
                        if record_id in records["ids"]:
                            pos = records["ids"].index(record_id)
                            for key in ("ids", "embeddings", "documents", "metadatas"):
                                records[key].pop(pos)
                    return httpx.Response(200, json=True)
                if action == "get":
                    include = set(body.get("include", []))
                    result: dict = {"ids": []}
                    for record_id in body.get("ids", []):
                        if record_id not in records["ids"]:
                            continue
                        pos = records["ids"].index(record_id)
                        result["ids"].append(record_id)
                        if "documents" in include:
                            result.setdefault("documents", []).append(records["documents"][pos])
                        if "metadatas" in include:
                            result.setdefault("metadatas", []).append(records["metadatas"][pos])
                        if "embeddings" in include:
                            result.setdefault("embeddings", []).append(records["embeddings"][pos])
                    for key in ("documents", "metadatas", "embeddings"):
                        result.setdefault(key, [])
                    return httpx.Response(200, json=result)
                if action == "query":
                    query = body["query_embeddings"][0]
                    n_results = body.get("n_results", 10)
                    include = set(body.get("include", []))
                    scored = []
                    for index, record_id in enumerate(records["ids"]):
                        distance = 1.0 - cosine_similarity(query, records["embeddings"][index])
                        scored.append((distance, index, record_id))
                    scored.sort(key=lambda item: item[0])
                    ids, distances, documents, metadatas, embeddings = [], [], [], [], []
                    for distance, index, record_id in scored[:n_results]:
                        ids.append(record_id)
                        distances.append(distance)
                        if "documents" in include:
                            documents.append(records["documents"][index])
                        if "metadatas" in include:
                            metadatas.append(records["metadatas"][index])
                        if "embeddings" in include:
                            embeddings.append(records["embeddings"][index])
                    return httpx.Response(
                        200,
                        json={
                            "ids": [ids],
                            "distances": [distances],
                            "documents": [documents],
                            "metadatas": [metadatas],
                            "embeddings": [embeddings],
                        },
                    )
        return httpx.Response(404, json={"error": "unhandled route"})

    return handler


@pytest.fixture
def chroma_store():
    state = ChromaState()
    store = make_http_store(
        "chroma",
        make_chroma_handler(state),
        base_url="http://localhost:8000",
    )
    return store, state


async def test_chroma_collection_and_documents(chroma_store) -> None:
    store, state = chroma_store
    assert await store.health() is True

    info = await store.create_collection("docs", dimension=2)
    assert info.name == "docs"
    assert info.namespace == "default"

    with pytest.raises(CollectionExistsError):
        await store.create_collection("docs", dimension=2)

    await store.add_documents(
        "docs",
        [
            VectorDocument(
                id="a", vector=[1.0, 0.0], text="one", metadata=VectorMetadata(values={"kind": "x"})
            ),
            VectorDocument(id="b", vector=[0.0, 1.0], text="two"),
        ],
    )
    assert (await store.stats("docs")).document_count == 2

    docs = await store.get_documents("docs", ["b", "zz"])
    assert [doc.id for doc in docs] == ["b"]
    assert docs[0].text == "two"

    results = await store.search("docs", SearchRequest(query_vector=[1.0, 0.0], top_k=2))
    assert [r.id for r in results] == ["a", "b"]
    assert results[0].text == "one"
    assert results[0].metadata.get("kind") == "x"
    assert abs(results[0].score - 1.0) < 1e-6

    assert await store.delete_documents("docs", ["a"]) == 1
    assert (await store.stats("docs")).document_count == 1

    listed = await store.list_collections()
    assert [c.name for c in listed] == ["docs"]

    await store.delete_collection("docs")
    assert await store.collection_info("docs") is None
    with pytest.raises(CollectionNotFoundError):
        await store.stats("docs")


async def test_chroma_update_bumps_version(chroma_store) -> None:
    store, _ = chroma_store
    await store.create_collection("docs", dimension=2)
    await store.add_documents("docs", [VectorDocument(id="a", vector=[1.0, 0.0], text="one")])
    assert (
        await store.update_documents(
            "docs", [VectorDocument(id="a", vector=[1.0, 0.0], text="one v2")]
        )
        == 1
    )
    docs = await store.get_documents("docs", ["a"])
    assert docs[0].version == 2
    assert docs[0].text == "one v2"


async def test_chroma_namespace_encoding(chroma_store) -> None:
    store, _ = chroma_store
    await store.create_collection("docs", dimension=2, namespace="tenant")
    await store.add_documents(
        "docs", [VectorDocument(id="a", vector=[1.0, 0.0])], namespace="tenant"
    )
    assert (await store.stats("docs", namespace="tenant")).document_count == 1
    assert len(await store.list_collections(namespace="tenant")) == 1


async def test_chroma_connection_error(chroma_store, monkeypatch) -> None:
    store, _ = chroma_store

    async def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(store._http._client, "request", boom)
    with pytest.raises(VectorStoreConnectionError):
        await store.health()
        await store.list_collections()
