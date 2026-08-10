"""Chat API tests: provider-interface routing, streaming, history, no-hallucination prompt.

The provider is always a mocked OpenAI-compatible transport — nothing real is
called, and every assertion proves the chat feature goes through the Provider
interface rather than any vendor SDK.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.chat_service import ChatService
from app.services.demo_source import build_simulated_snapshot
from app.services.router_tool import RouterTool
from app.services.router_tool_executor import RouterToolResult
from providers.factory import ProviderManager
from providers.openai import OpenAIProvider
from tests.auth import admin_headers
from tests.unit.providers_helpers import make_provider

SNAPSHOT = build_simulated_snapshot()


class FakeSnapshotService:
    def __init__(self, update: DashboardUpdate | None) -> None:
        self._update = update

    def latest(self) -> DashboardUpdate | None:
        return self._update


def _router_update() -> DashboardUpdate:
    return DashboardUpdate(
        type="update",
        sequence=1,
        sent_at=datetime.now(UTC),
        source="simulated",
        device_id="demo-router",
        connected=True,
        snapshot=build_simulated_snapshot(),
    )


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
def _client(
    manager: ProviderManager,
    *,
    snapshot=SNAPSHOT,
    snapshot_service=None,
) -> TestClient:
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        service = ChatService(manager, lambda: snapshot)
        if snapshot_service is not None:
            service = ChatService(
                manager,
                lambda: snapshot,
                router_tool=RouterTool(snapshot_service.latest),
            )
            app.state.snapshot_service = snapshot_service
        app.state.chat_service = service
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
        response = client.post(
            "/api/v1/chat/stream",
            json={"session_id": "s4", "message": "stream"},
        )
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


# ── router-aware chat ─────────────────────────────────────────────────────────


def test_chat_auto_detect_injects_router_context() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra1",
                "message": "show router system, cpu, memory, storage and network",
            },
        )
    assert response.status_code == 200
    assert response.json()["reply"] == "Hello router"

    sent = seen["messages"]
    assert sent[0]["role"] == "system"
    assert "### Router Context" in sent[0]["content"]
    assert "### End Router Context" in sent[0]["content"]
    assert "prefer factual values from it over model assumptions" in sent[0]["content"]
    assert "Never invent router values" in sent[0]["content"]
    assert "## Router" in sent[0]["content"]
    assert "- Hostname: demo-router" in sent[0]["content"]
    assert "## CPU" in sent[0]["content"]
    assert "## Memory" in sent[0]["content"]
    assert "## Storage" in sent[0]["content"]
    assert "## Network Interfaces" in sent[0]["content"]
    context = response.json()["router_context"]
    assert context is not None
    assert "## Router" in context
    assert "- Hostname: demo-router" in context
    message = "show router system, cpu, memory, storage and network"
    assert sent[-1] == {"role": "user", "content": message}


def test_chat_auto_detect_skips_non_router_context() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra2",
                "message": "hello there, how are you?",
            },
        )
    assert response.status_code == 200
    assert response.json()["router_context"] is None
    sent = seen["messages"]
    assert "### Router Context" not in sent[0]["content"]
    assert "### End Router Context" not in sent[0]["content"]


def test_chat_router_aware_unavailable_router_continues() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(None),
    ) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra3",
                "message": "show router cpu usage",
                "router_aware": True,
            },
        )
    assert response.status_code == 200
    assert response.json()["reply"] == "Hello router"
    assert response.json()["router_context"] is None
    sent = seen["messages"]
    assert "### Router Context" not in sent[0]["content"]
    assert "### End Router Context" not in sent[0]["content"]


def test_chat_stream_auto_detect_injects_router_context() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "session_id": "ra4",
                "message": "show router system, cpu, memory, storage and network",
            },
        )
    assert response.status_code == 200
    assert '"type": "done"' in response.text
    assert '"router_context"' in response.text
    sent = seen["messages"]
    assert sent[0]["role"] == "system"
    assert "### Router Context" in sent[0]["content"]
    assert "### End Router Context" in sent[0]["content"]


def _sse_events(text: str) -> list[dict]:
    return [
        json.loads(raw.split("data:", 1)[1])
        for raw in text.split("\n\n")
        if raw.startswith("data:")
    ]


def test_chat_stream_router_context_emitted_once_on_done() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "session_id": "ra11",
                "message": "show router system, cpu, memory, storage and network",
            },
        )
    assert response.status_code == 200
    assert response.text.count('"router_context"') == 1
    events = _sse_events(response.text)
    done = [event for event in events if event["type"] == "done"]
    deltas = [event for event in events if event["type"] == "delta"]
    assert len(done) == 1
    assert done[0]["router_context"] is not None
    assert "## Router" in done[0]["router_context"]
    assert all("router_context" not in event for event in deltas)


def test_chat_stream_tokens_remain_unchanged() -> None:
    seen: dict = {}
    with _client(_manager(seen)) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"session_id": "ra12", "message": "stream"},
        )
    assert response.status_code == 200
    events = _sse_events(response.text)
    deltas = [event["content"] for event in events if event["type"] == "delta"]
    assert deltas == ["Hello", " router"]
    done = [event for event in events if event["type"] == "done"][0]
    assert done["reply"] == "Hello router"


def test_chat_stream_without_router_context_stays_null() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={
                "session_id": "ra13",
                "message": "hello there, how are you?",
            },
        )
    assert response.status_code == 200
    events = _sse_events(response.text)
    done = [event for event in events if event["type"] == "done"][0]
    assert done["router_context"] is None
    assert done["reply"] == "Hello router"


def test_chat_router_aware_no_router_intent_skips_tool() -> None:
    seen: dict = {}
    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra5",
                "message": "hello there",
                "router_aware": True,
            },
        )
    assert response.status_code == 200
    assert response.json()["reply"] == "Hello router"
    sent = seen["messages"]
    assert "### Router Context" not in sent[0]["content"]
    assert "### End Router Context" not in sent[0]["content"]


def test_chat_router_aware_executes_through_executor() -> None:
    seen: dict = {}
    calls: list[str] = []

    class RecordingExecutor:
        def execute(self, requests: list[str]):
            calls.extend(requests)
            return [
                RouterToolResult(name=name, ok=True, result={"hostname": "demo-router"})
                for name in requests
            ]

    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        service = client.app.state.chat_service
        service._executor = RecordingExecutor()  # noqa: SLF001
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra6",
                "message": "show router system",
                "router_aware": True,
            },
        )
    assert response.status_code == 200
    assert response.json()["reply"] == "Hello router"
    assert calls == ["system"]
    sent = seen["messages"]
    assert "### Router Context" in sent[0]["content"]
    assert "### End Router Context" in sent[0]["content"]


def test_chat_router_aware_reuses_cached_results() -> None:
    seen: dict = {}
    calls: list[str] = []

    class CountingExecutor:
        def execute(self, requests: list[str]):
            calls.extend(requests)
            return [
                RouterToolResult(name=name, ok=True, result={"hostname": "demo-router"})
                for name in requests
            ]

    with _client(
        _manager(seen),
        snapshot_service=FakeSnapshotService(_router_update()),
    ) as client:
        service = client.app.state.chat_service
        service._executor = CountingExecutor()  # noqa: SLF001
        client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra7",
                "message": "show router system",
                "router_aware": True,
            },
        )
        client.post(
            "/api/v1/chat",
            json={
                "session_id": "ra7",
                "message": "show router hostname",
                "router_aware": True,
            },
        )
    assert calls == ["system"]
    assert service._cache.stats()["hits"] >= 1  # noqa: SLF001


def test_compose_accepts_router_context() -> None:
    service = ChatService(ProviderManager({}), lambda: SNAPSHOT)
    request = service.compose(
        message="hi",
        history=[],
        router_context="# Router markdown",
    )
    assert request.messages[0].role == "system"
    assert "### Router Context" in request.messages[0].content
    assert "### End Router Context" in request.messages[0].content
    assert "# Router markdown" in request.messages[0].content
    assert request.messages[-1].content == "hi"


def test_compose_injects_router_context_section() -> None:
    service = ChatService(ProviderManager({}), lambda: SNAPSHOT)
    request = service.compose(
        message="hi",
        history=[],
        router_context="# Router markdown",
    )
    system = request.messages[0].content
    section = system.split("### Router Context\n", 1)[1].split(
        "\n### End Router Context",
        1,
    )[0]
    assert section.strip() == "# Router markdown"


def test_compose_without_router_context_keeps_prompt_unchanged() -> None:
    service = ChatService(ProviderManager({}), lambda: SNAPSHOT)
    plain = service.compose(message="hi", history=[])
    with_context = service.compose(
        message="hi",
        history=[],
        router_context="# Router markdown",
    )
    assert plain.messages[0].content == service.system_prompt()
    assert "### Router Context" not in plain.messages[0].content
    assert "### Router Context" in with_context.messages[0].content
