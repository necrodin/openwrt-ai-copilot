"""Qdrant backend tests using a stateful ``httpx.MockTransport``.

The mock emulates the Qdrant REST API subset the adapter uses, so the tests
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
class QdrantState:
    collections: dict = field(default_factory=dict)


def _unquote(segment: str) -> str:
    from urllib.parse import unquote

    return unquote(segment)


def make_qdrant_handler(state: QdrantState):
    async def handler(request: httpx.Request) -> httpx.Response:
        method = request.method
        path = request.url.path
        parts = [p for p in path.split("/") if p]
        if method == "GET" and path == "/collections":
            return httpx.Response(
                200,
                json={"result": {"collections": [{"name": qn} for qn in state.collections]}},
            )
        if method == "PUT" and len(parts) == 2 and parts[0] == "collections":
            qn = _unquote(parts[1])
            if qn in state.collections:
                return httpx.Response(409, json={"status": {"error": "exists"}})
            body = json.loads(request.content)
            state.collections[qn] = {
                "size": body["vectors"]["size"],
                "metadata": body.get("metadata", {}),
                "created_at": "2026-01-01T00:00:00Z",
                "points": {},
            }
            return httpx.Response(200, json={"result": True})
        if method == "DELETE" and len(parts) == 2 and parts[0] == "collections":
            qn = _unquote(parts[1])
            state.collections.pop(qn, None)
            return httpx.Response(200, json={"result": True})
        if method == "GET" and len(parts) == 2 and parts[0] == "collections":
            qn = _unquote(parts[1])
            entry = state.collections.get(qn)
            if entry is None:
                return httpx.Response(404, json={"status": {"error": "not found"}})
            return httpx.Response(
                200,
                json={
                    "result": {
                        "status": "green",
                        "metadata": entry["metadata"],
                        "vectors_count": len(entry["points"]),
                        "created_at": entry["created_at"],
                        "config": {"params": {"vectors": {"size": entry["size"]}}},
                    }
                },
            )
        if method == "PUT" and len(parts) == 3 and parts[2] == "points":
            qn = _unquote(parts[1])
            body = json.loads(request.content)
            entry = state.collections.setdefault(qn, {"points": {}})
            for point in body["points"]:
                entry["points"][point["id"]] = {
                    "vector": point["vector"],
                    "payload": point.get("payload", {}),
                }
            return httpx.Response(200, json={"result": {"operation_id": 1, "status": "completed"}})
        if method == "POST" and len(parts) == 4 and parts[2] == "points" and parts[3] == "delete":
            qn = _unquote(parts[1])
            body = json.loads(request.content)
            entry = state.collections.get(qn, {"points": {}})
            for point_id in body["points"]:
                entry["points"].pop(point_id, None)
            return httpx.Response(200, json={"result": {"operation_id": 2, "status": "completed"}})
        if method == "POST" and len(parts) == 4 and parts[2] == "points" and parts[3] == "search":
            qn = _unquote(parts[1])
            body = json.loads(request.content)
            entry = state.collections.get(qn, {"points": {}})
            scored = []
            for point_id, point in entry["points"].items():
                score = cosine_similarity(body["vector"], point["vector"])
                scored.append((score, point_id, point))
            scored.sort(key=lambda item: item[0], reverse=True)
            result = []
            for score, point_id, point in scored[: body.get("limit", 10)]:
                item = {"id": point_id, "score": score, "payload": point["payload"]}
                if body.get("with_vector"):
                    item["vector"] = point["vector"]
                result.append(item)
            return httpx.Response(200, json={"result": result})
        if method == "POST" and len(parts) == 4 and parts[2] == "points" and parts[3] == "scroll":
            qn = _unquote(parts[1])
            body = json.loads(request.content)
            entry = state.collections.get(qn, {"points": {}})
            points = []
            for point_id, point in entry["points"].items():
                item = {"id": point_id, "payload": point["payload"]}
                if body.get("with_vector"):
                    item["vector"] = point["vector"]
                points.append(item)
            return httpx.Response(
                200, json={"result": {"points": points, "next_page_offset": None}}
            )
        if method == "POST" and len(parts) == 3 and parts[2] == "points":
            qn = _unquote(parts[1])
            body = json.loads(request.content)
            entry = state.collections.get(qn, {"points": {}})
            result = []
            for point_id in body["ids"]:
                point = entry["points"].get(point_id)
                if point is None:
                    continue
                item = {"id": point_id, "payload": point["payload"]}
                if body.get("with_vector"):
                    item["vector"] = point["vector"]
                result.append(item)
            return httpx.Response(200, json={"result": result})
        return httpx.Response(404, json={"status": {"error": "unhandled route"}})

    return handler


@pytest.fixture
def qdrant_store():
    state = QdrantState()
    store = make_http_store(
        "qdrant",
        make_qdrant_handler(state),
        base_url="http://localhost:6333",
    )
    return store, state


async def test_qdrant_collection_and_documents(qdrant_store) -> None:
    store, state = qdrant_store
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

    results = await store.search("docs", SearchRequest(query_vector=[1.0, 0.0], top_k=2))
    assert [r.id for r in results] == ["a", "b"]
    assert results[0].text == "one"
    assert results[0].metadata.get("kind") == "x"

    assert await store.delete_documents("docs", ["a"]) == 1
    assert (await store.stats("docs")).document_count == 1

    listed = await store.list_collections()
    assert [c.name for c in listed] == ["docs"]

    await store.delete_collection("docs")
    assert await store.collection_info("docs") is None
    with pytest.raises(CollectionNotFoundError):
        await store.stats("docs")


async def test_qdrant_update_bumps_version(qdrant_store) -> None:
    store, _ = qdrant_store
    await store.create_collection("docs", dimension=2)
    await store.add_documents("docs", [VectorDocument(id="a", vector=[1.0, 0.0], text="one")])
    assert (
        await store.update_documents(
            "docs", [VectorDocument(id="a", vector=[1.0, 0.0], text="one v2")]
        )
        == 1
    )
    assert (
        await store.update_documents(
            "docs", [VectorDocument(id="b", vector=[0.0, 1.0], text="new")]
        )
        == 1
    )
    docs = await store.get_documents("docs", ["a", "b"])
    assert docs[0].version == 2
    assert docs[1].version == 1


async def test_qdrant_namespace_encoding(qdrant_store) -> None:
    store, _ = qdrant_store
    await store.create_collection("docs", dimension=2, namespace="tenant")
    await store.add_documents(
        "docs", [VectorDocument(id="a", vector=[1.0, 0.0])], namespace="tenant"
    )
    assert (await store.stats("docs", namespace="tenant")).document_count == 1
    assert len(await store.list_collections(namespace="default")) == 0
    assert len(await store.list_collections(namespace="tenant")) == 1


async def test_qdrant_connection_error(qdrant_store, monkeypatch) -> None:
    store, _ = qdrant_store

    async def boom(*args, **kwargs):
        raise httpx.ConnectError("down")

    monkeypatch.setattr(store._http._client, "request", boom)
    with pytest.raises(VectorStoreConnectionError):
        await store.list_collections()
