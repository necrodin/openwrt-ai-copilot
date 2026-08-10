"""Chat API RAG tests: grounded, cited answers routed through the RAG service.

The full stack is exercised with mocked transports (embedding, rerank, chat) and
a real SQLite vector store seeded with documents — nothing is called externally.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.chat_service import ChatService
from providers.factory import ProviderManager
from providers.nim import NIMProvider
from providers.openai import OpenAIProvider
from rag.ai import RAGConfiguration
from tests.auth import admin_headers
from tests.unit.providers_helpers import make_provider
from vectorstore.models import VectorDocument, VectorMetadata

WIREGUARD_DOC = VectorDocument(
    id="wireguard#0",
    vector=[1.0, 0.0],
    text="WireGuard uses Curve25519 for its key exchange.",
    metadata=VectorMetadata(
        values={
            "document_id": "wireguard",
            "index": 0,
            "heading": "Crypto",
            "source": "knowledge/docs/wireguard.md",
            "title": "wireguard.md",
            "reference": "",
            "format": "md",
            "language": "en",
            "checksum": "",
            "version": 1,
        }
    ),
)

FIREWALL_DOC = VectorDocument(
    id="firewall#0",
    vector=[0.0, 1.0],
    text="OpenWrt firewall rules are expressed with nftables.",
    metadata=VectorMetadata(
        values={
            "document_id": "firewall",
            "index": 0,
            "heading": "",
            "source": "knowledge/docs/firewall.md",
            "title": "firewall.md",
            "reference": "",
            "format": "md",
            "language": "en",
            "checksum": "",
            "version": 1,
        }
    ),
)


def _handler(seen: dict[str, Any]):
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/embeddings"):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "model": "embed",
                    "data": [{"embedding": [0.5, 0.5]} for _ in body["input"]],
                    "usage": {"prompt_tokens": len(body["input"]), "completion_tokens": 0},
                },
            )
        if path.endswith("/rerank"):
            seen["rerank_calls"] = seen.get("rerank_calls", 0) + 1
            body = json.loads(request.content)
            docs = body["documents"]
            return httpx.Response(
                200,
                json={
                    "model": "rerank",
                    "results": [
                        {"index": i, "relevance_score": 1.0 - i * 0.1, "document": docs[i]}
                        for i in range(len(docs))
                    ],
                    "prompt_tokens": 1,
                    "completion_tokens": 0,
                },
            )
        body = json.loads(request.content)
        seen["messages"] = body["messages"]
        if body.get("stream"):
            return httpx.Response(
                200,
                text=(
                    'data: {"model":"rag-m","choices":[{"delta":{"content":"Grounded "}}]}\n\n'
                    'data: {"model":"rag-m","choices":[{"delta":{"content":"answer [1]"}}]}\n\n'
                    'data: {"model":"rag-m","choices":[{"delta":{},"finish_reason":"stop"}]}\n\n'
                    "data: [DONE]\n\n"
                ),
            )
        return httpx.Response(
            200,
            json={
                "model": "rag-m",
                "choices": [{"message": {"role": "assistant", "content": "Grounded answer [1]"}}],
                "usage": {"prompt_tokens": 42, "completion_tokens": 4},
            },
        )

    return handler


def _manager(seen: dict[str, Any]) -> ProviderManager:
    provider = make_provider(OpenAIProvider, _handler(seen), name="rag", model="rag-m")
    nim = make_provider(
        NIMProvider,
        _handler(seen),
        name="nim",
        model="rag-m",
        rerank_model="nvidia/rerank",
    )
    return ProviderManager({"rag": provider, "nim": nim}, default_provider="rag")


async def _service(
    tmp_path,
    seen: dict[str, Any],
    *,
    rerank: bool = False,
) -> Any:
    from app.services.rag_service import RAGService

    config = RAGConfiguration(
        collection="documents",
        top_k=4,
        max_documents=4,
        vector_dimensions=2,
        provider="rag",
        rerank_provider="nim" if rerank else None,
        rerank_model="nvidia/rerank" if rerank else None,
    )
    manager = _manager(seen)
    service = await RAGService.create(
        manager,
        config,
        vector_store_path=str(tmp_path / "vectors.sqlite3"),
    )
    await service._vector_store.add_documents(
        config.collection,
        [WIREGUARD_DOC, FIREWALL_DOC],
        namespace=config.namespace,
    )
    return service


def _client(service) -> TestClient:
    app = create_app()
    client = TestClient(app, headers=admin_headers())
    client.__enter__()
    client.app.state.chat_service = ChatService(service._manager, lambda: None)
    client.app.state.rag_service = service
    return client


async def test_rag_chat_returns_grounded_cited_answer(tmp_path) -> None:
    seen: dict[str, Any] = {}
    service = await _service(tmp_path, seen)
    client = _client(service)
    try:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "r1", "message": "how does wireguard work?"},
        )
    finally:
        client.__exit__(None, None, None)
        await service.aclose()

    assert response.status_code == 200
    body = response.json()
    assert body["rag"] is True
    assert body["reply"] == "Grounded answer [1]"
    assert body["provider"] == "rag"
    assert body["model"] == "rag-m"
    assert body["usage"]["chunks_retrieved"] == 2

    citations = body["citations"]
    assert len(citations) == 2
    by_id = {citation["chunk_id"]: citation for citation in citations}
    wireguard = by_id["wireguard#0"]
    assert wireguard["source"] == "knowledge/docs/wireguard.md"
    assert wireguard["document"] == "wireguard.md"
    assert wireguard["section"] == "Crypto"
    assert wireguard["similarity_score"] > 0.9
    assert wireguard["rerank_score"] is None
    assert wireguard["confidence"] == wireguard["similarity_score"]

    sent = seen["messages"]
    assert sent[-1]["role"] == "user"
    assert "Context:" in sent[-1]["content"]
    assert "Question:" in sent[-1]["content"]
    assert "WireGuard uses Curve25519" in sent[-1]["content"]
    # no rerank configured -> provider rerank endpoint never hit
    assert seen.get("rerank_calls") is None


async def test_rag_chat_with_reranker_uses_rerank_scores(tmp_path) -> None:
    seen: dict[str, Any] = {}
    service = await _service(tmp_path, seen, rerank=True)
    client = _client(service)
    try:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "r2", "message": "firewall question"},
        )
    finally:
        client.__exit__(None, None, None)
        await service.aclose()

    assert response.status_code == 200
    assert response.json()["rag"] is True
    assert seen.get("rerank_calls") == 1
    citations = response.json()["citations"]
    assert [citation["confidence"] for citation in citations] == [1.0, 0.9]
    assert [citation["rerank_score"] for citation in citations] == [1.0, 0.9]
    # the vector-store similarity is preserved alongside the rerank score
    assert all(citation["similarity_score"] == 1.0 for citation in citations)


async def test_rag_chat_stream_emits_delta_citations_done(tmp_path) -> None:
    seen: dict[str, Any] = {}
    service = await _service(tmp_path, seen)
    client = _client(service)
    try:
        response = client.post(
            "/api/v1/chat/stream",
            json={"session_id": "r3", "message": "stream question"},
        )
        history = client.get("/api/v1/chat/history", params={"session_id": "r3"})
    finally:
        client.__exit__(None, None, None)
        await service.aclose()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert '"type": "delta"' in text
    assert '"type": "citations"' in text
    assert '"type": "done"' in text
    assert '"reply": "Grounded answer [1]"' in text
    assert '"rag": true' in text
    assert "knowledge/docs/wireguard.md" in text

    messages = history.json()["messages"]
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "Grounded answer [1]"


async def test_rag_chat_memory_persists_across_turns(tmp_path) -> None:
    seen: dict[str, Any] = {}
    service = await _service(tmp_path, seen)
    client = _client(service)
    try:
        client.post("/api/v1/chat", json={"session_id": "m1", "message": "turn one"})
        client.post("/api/v1/chat", json={"session_id": "m1", "message": "turn two"})
    finally:
        client.__exit__(None, None, None)
        await service.aclose()

    roles = [message["role"] for message in seen["messages"]]
    assert roles == ["system", "user", "assistant", "user"]
    assert "turn one" in seen["messages"][1]["content"]
    assert seen["messages"][2]["content"] == "Grounded answer [1]"
    assert "turn two" in seen["messages"][3]["content"]


def test_rag_disabled_by_default() -> None:
    """Without a rag.yaml the app boots with RAG chat disabled."""
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        assert client.app.state.rag_service is None
