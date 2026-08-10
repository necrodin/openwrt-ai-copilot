"""Router-isolation regression tests: chat session context is bound to a principal.

Two authenticated principals (distinct browser sessions, or a session versus a
static key) must never share chat history, session listings, or RAG conversation
memory — even when they submit the same client-controlled ``session_id``. These
tests lock in the owner-namespacing fix against the cross-principal history
exfiltration path.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager

import httpx
from fastapi.testclient import TestClient

from app.db.chat_store import ChatStore
from app.main import create_app
from app.services.chat_service import ChatService
from providers.factory import ProviderManager
from providers.openai import OpenAIProvider
from tests.auth import TEST_ADMIN_KEY, TEST_READONLY_KEY
from tests.unit.providers_helpers import make_provider


def _handler_for(seen: dict) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        seen["messages"] = json.loads(request.content).get("messages", [])
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            },
        )

    return handler


def _manager(seen: dict) -> ProviderManager:
    provider = make_provider(
        OpenAIProvider,
        _handler_for(seen),
        name="primary",
        model="gpt-4o-mini",
    )
    return ProviderManager({"primary": provider}, default_provider="primary")


@contextmanager
def _make_client(seen: dict) -> TestClient:
    app = create_app()
    with TestClient(app, headers={}) as client:
        client.app.state.chat_service = ChatService(_manager(seen), lambda: None)
        yield client


def _login(client: TestClient, key: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"api_key": key})
    assert response.status_code == 200
    return {"Authorization": f"Bearer {response.json()['token']}"}


def _chat(client: TestClient, headers: dict[str, str], session_id: str, message: str) -> None:
    response = client.post(
        "/api/v1/chat",
        json={"session_id": session_id, "message": message},
        headers=headers,
    )
    assert response.status_code == 200


def _history(client: TestClient, headers: dict[str, str], session_id: str) -> list[dict]:
    response = client.get(
        "/api/v1/chat/history",
        params={"session_id": session_id},
        headers=headers,
    )
    assert response.status_code == 200
    return response.json()["messages"]


# ── cross-principal isolation ──────────────────────────────────────────────


def test_two_browser_sessions_do_not_share_chat_history() -> None:
    seen: dict = {}
    with _make_client(seen) as client:
        headers_a = _login(client, TEST_ADMIN_KEY)
        headers_b = _login(client, TEST_ADMIN_KEY)
        _chat(client, headers_a, "iso-shared", "private-a")

        assert [m["role"] for m in _history(client, headers_b, "iso-shared")] == []
        assert [m["content"] for m in _history(client, headers_a, "iso-shared")] == [
            "private-a",
            "ok",
        ]


def test_sessions_listing_is_scoped_to_the_caller() -> None:
    seen: dict = {}
    with _make_client(seen) as client:
        headers_a = _login(client, TEST_ADMIN_KEY)
        headers_b = _login(client, TEST_ADMIN_KEY)
        _chat(client, headers_a, "iso-own-session", "hi")

        ids_b = {s["session_id"] for s in client.get(
            "/api/v1/chat/sessions", headers=headers_b
        ).json()["sessions"]}
        ids_a = {s["session_id"] for s in client.get(
            "/api/v1/chat/sessions", headers=headers_a
        ).json()["sessions"]}
        assert "iso-own-session" in ids_a
        assert "iso-own-session" not in ids_b


def test_cross_principal_chat_cannot_exfiltrate_history_into_llm() -> None:
    seen: dict = {}
    with _make_client(seen) as client:
        headers_a = _login(client, TEST_ADMIN_KEY)
        headers_b = _login(client, TEST_ADMIN_KEY)
        secret = "GSR-CONFIDENTIAL-99"
        _chat(client, headers_a, "iso-exfil", secret)

        _chat(client, headers_b, "iso-exfil", "hello")
        sent = seen["messages"]
        user_turns = [m["content"] for m in sent if m["role"] == "user"]
        assert user_turns == ["hello"]
        assert secret not in json.dumps(sent)

        a_still_has = [m["content"] for m in _history(client, headers_a, "iso-exfil")]
        assert secret in a_still_has
        assert "hello" not in a_still_has


def test_static_readonly_key_cannot_read_static_admin_history() -> None:
    seen: dict = {}
    with _make_client(seen) as client:
        admin_headers = {"Authorization": f"Bearer {TEST_ADMIN_KEY}"}
        readonly_headers = {"Authorization": f"Bearer {TEST_READONLY_KEY}"}
        _chat(client, admin_headers, "iso-key-scope", "admin-only")

        assert [m["content"] for m in _history(client, readonly_headers, "iso-key-scope")] == []
        assert [m["content"] for m in _history(client, admin_headers, "iso-key-scope")] == [
            "admin-only",
            "ok",
        ]


# ── router reference surface ───────────────────────────────────────────────


def test_unknown_router_id_gets_no_router_context() -> None:
    from app.services.router_manager import RouterManager
    from app.services.router_tool import RouterTool

    router_manager = RouterManager()
    router_manager.register("default", RouterTool(lambda: None), default=True)
    service = ChatService(ProviderManager({}), lambda: None, router_manager=router_manager)

    context = service.router_context_markdown(
        "show router system",
        router_aware=True,
        session_id="iso-router-ref",
        router_id="someone-elses-router",
    )
    assert context is None


# ── store-level owner scoping ─────────────────────────────────────────────


def test_chat_store_scopes_reads_and_listing_by_owner() -> None:
    store = ChatStore()
    shared = "iso-store-shared"
    private = "iso-store-private"
    store.add_message(session_id=shared, role="user", content="for-a", owner="alice")
    store.add_message(session_id=shared, role="user", content="for-b", owner="bob")
    store.add_message(session_id=private, role="user", content="alice-only", owner="alice")

    # Reads never cross owners, even on a shared session id.
    assert [m.content for m in store.get_messages(shared, owner="alice")] == ["for-a"]
    assert [m.content for m in store.get_messages(shared, owner="bob")] == ["for-b"]
    assert [m.content for m in store.get_messages(shared, owner="carol")] == []

    # Session listings are owner-scoped.
    alice_sessions = {s["session_id"] for s in store.list_sessions(owner="alice")}
    bob_sessions = {s["session_id"] for s in store.list_sessions(owner="bob")}
    carol_sessions = {s["session_id"] for s in store.list_sessions(owner="carol")}
    assert shared in alice_sessions
    assert shared in bob_sessions
    assert private in alice_sessions
    assert private not in bob_sessions
    assert carol_sessions == set()


# ── RAG conversation memory isolation ─────────────────────────────────────


def test_rag_engine_isolation_by_principal() -> None:
    from app.services.rag_service import RAGService
    from rag.ai import RAGConfiguration

    service = RAGService.__new__(RAGService)
    service._retrieval_engines = {}
    service._reranker = None
    service._cache = None
    service._retriever = None
    service.config = RAGConfiguration()

    engine_a = service._retrieval_engine("subject-a", "shared-session")
    engine_a_again = service._retrieval_engine("subject-a", "shared-session")
    engine_b = service._retrieval_engine("subject-b", "shared-session")

    assert engine_a is engine_a_again
    assert engine_b is not engine_a

    service.seed_history("subject-a", "shared-session", [("user", "private-from-a")])
    assert engine_b.memory.state("shared-session") is None
    assert engine_a.memory.state("shared-session") is not None