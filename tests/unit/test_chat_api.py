"""Chat API tests: provider-interface routing, streaming, history, no-hallucination prompt.

The provider is always a mocked OpenAI-compatible transport — nothing real is
called, and every assertion proves the chat feature goes through the Provider
interface rather than any vendor SDK.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.chat_service import ChatService
from app.services.demo_source import build_simulated_snapshot
from providers.factory import ProviderManager
from providers.openai import OpenAIProvider
from tests.unit.providers_helpers import make_provider

SNAPSHOT = build_simulated_snapshot()


def _handler_for(seen: dict) -> Callable[[httpx.Request], httpx.Response]:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["messages"] = body["messages"]
        if body.get("stream"):
            return httpx.Response(
                200,
                text=(
                    'data: {"model":"gpt-4o-mini","choices":[{"delta":{"content":"Hello"}}]}\n\n'
                    'data: {"model":"gpt-4o-mini","choices":[{"delta":{"content":" router"}}]}\n\n'
                    'data: {"model":"gpt-4o-mini","choices":'
                    '[{"delta":{},"finish_reason":"stop"}]}\n\n'
                    "data: [DONE]\n\n"
                ),
            )
        return httpx.Response(
            200,
            json={
                "model": "gpt-4o-mini",
                "choices": [{"message": {"role": "assistant", "content": "Hello router"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 2},
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
def _client(manager: ProviderManager, *, snapshot=SNAPSHOT) -> TestClient:
    app = create_app()
    with TestClient(app) as client:
        app.state.chat_service = ChatService(manager, lambda: snapshot)
        yield client


def test_system_prompt_includes_router_state() -> None:
    service = ChatService(ProviderManager({}), lambda: SNAPSHOT)
    prompt = service.system_prompt()
    assert "ROUTER STATE" in prompt
    assert '"hostname": "demo-router"' in prompt
    assert "Never invent" in prompt
    assert "read-only" in prompt


def test_system_prompt_without_router_data() -> None:
    service = ChatService(ProviderManager({}), lambda: None)
    prompt = service.system_prompt()
    assert "No router state is available" in prompt


def test_chat_uses_provider_interface_and_records_history() -> None:
    seen: dict = {}
    with _client(_manager(seen)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "s1", "message": "hi"},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello router"
    assert body["provider"] == "primary"
    assert body["model"] == "gpt-4o-mini"
    assert body["usage"]["prompt_tokens"] == 11

    sent = seen["messages"]
    assert sent[0]["role"] == "system"
    assert "ROUTER STATE" in sent[0]["content"]
    assert sent[-1] == {"role": "user", "content": "hi"}


def test_chat_history_persists_and_feeds_context() -> None:
    seen: dict = {}
    with _client(_manager(seen)) as client:
        client.post("/api/v1/chat", json={"session_id": "s2", "message": "first"})
        history = client.get("/api/v1/chat/history", params={"session_id": "s2"})
    assert history.status_code == 200
    messages = history.json()["messages"]
    assert [(m["role"], m["content"]) for m in messages] == [
        ("user", "first"),
        ("assistant", "Hello router"),
    ]


def test_chat_history_included_in_second_turn() -> None:
    seen: dict = {}
    with _client(_manager(seen)) as client:
        client.post("/api/v1/chat", json={"session_id": "s3", "message": "turn one"})
        client.post("/api/v1/chat", json={"session_id": "s3", "message": "turn two"})
    sent = seen["messages"]
    assert [m["role"] for m in sent] == ["system", "user", "assistant", "user"]
    assert sent[1]["content"] == "turn one"
    assert sent[2]["content"] == "Hello router"
    assert sent[3]["content"] == "turn two"


def test_chat_stream_deltas_and_persists_reply() -> None:
    seen: dict = {}
    with _client(_manager(seen)) as client:
        response = client.post("/api/v1/chat/stream", json={"session_id": "s4", "message": "stream"})
        history = client.get("/api/v1/chat/history", params={"session_id": "s4"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert '"type": "delta"' in text
    assert '"type": "done"' in text
    assert '"reply": "Hello router"' in text
    messages = history.json()["messages"]
    assert messages[-1]["role"] == "assistant"
    assert messages[-1]["content"] == "Hello router"


def test_chat_without_provider_returns_503() -> None:
    with _client(ProviderManager({})) as client:
        response = client.post("/api/v1/chat", json={"message": "hi"})
    assert response.status_code == 503
    assert "chat" in response.json()["detail"]


def test_chat_stream_without_provider_emits_error_event() -> None:
    with _client(ProviderManager({})) as client:
        response = client.post("/api/v1/chat/stream", json={"message": "hi"})
    assert response.status_code == 200
    assert '"type": "error"' in response.text


def test_chat_sessions_lists_known_sessions() -> None:
    seen: dict = {}
    with _client(_manager(seen)) as client:
        client.post("/api/v1/chat", json={"session_id": "session-list", "message": "hi"})
        sessions = client.get("/api/v1/chat/sessions")
    body = sessions.json()
    ids = [session["session_id"] for session in body["sessions"]]
    assert "session-list" in ids
