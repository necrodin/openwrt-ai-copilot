"""End-to-end router pipeline tests.

Exercises the full deterministic pipeline with real components and mocked AI
transports only:

    Intent Detection -> Router Manager -> Tool Executor -> Snapshot
        -> Diagnosis -> Recommendation -> Router Context
        -> System Prompt -> Final Chat Response

Every scenario builds a deterministic :class:`DeviceSnapshot`, registers a real
:class:`RouterManager` over it (exactly like ``app.main``), and asserts on the
provider request actually sent plus the API response. Nothing real is called.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

import httpx
from fastapi.testclient import TestClient

from app.main import create_app
from app.schemas.dashboard import DashboardUpdate
from app.services.chat_service import ChatService
from app.services.router_diagnosis import RouterDiagnosisEngine
from app.services.router_manager import RouterManager
from app.services.router_recommendation import RouterRecommendationEngine
from app.services.router_snapshot import RouterSnapshot
from app.services.router_tool import RouterTool
from providers.factory import ProviderManager
from providers.openai import OpenAIProvider
from router_agent.model import (
    CpuInfo,
    DeviceSnapshot,
    KernelInfo,
    MemoryInfo,
    NetworkAddress,
    NetworkInterface,
    SnapshotMeta,
    StorageMount,
    WifiInfo,
    WifiRadio,
)
from tests.auth import admin_headers
from tests.unit.providers_helpers import make_provider
from vectorstore.models import VectorDocument, VectorMetadata

# --------------------------------------------------------------------------- #
# Deterministic router scenarios                                              #
# --------------------------------------------------------------------------- #

_TOTAL_KB = 8 * 1024 * 1024
_GIB = 1024**3


def _meta() -> SnapshotMeta:
    return SnapshotMeta(
        collected_at=datetime.now(UTC),
        device_id="demo-router",
        transport="simulated",
        board="x86/64",
        model="Demo OpenWrt x86/64",
        firmware="SNAPSHOT",
    )


def _kernel() -> KernelInfo:
    return KernelInfo(
        kernel="6.6.80",
        release="SNAPSHOT",
        hostname="demo-router",
        model="Demo OpenWrt x86/64",
        architecture="x86_64",
        board="x86/64",
        system="Generic",
        version="1.0",
    )


def _memory(used_percent: float) -> MemoryInfo:
    used_kb = int(_TOTAL_KB * used_percent / 100.0)
    return MemoryInfo(
        total_kb=_TOTAL_KB,
        free_kb=_TOTAL_KB - used_kb,
        used_kb=used_kb,
        buffered_kb=0,
        cached_kb=0,
        available_kb=_TOTAL_KB - used_kb,
    )


def _storage(use_percent: float) -> list[StorageMount]:
    total = int(64 * _GIB)
    used = int(total * use_percent / 100.0)
    return [
        StorageMount(
            device="/dev/sda1",
            mountpoint="/overlay",
            filesystem="ext4",
            total_bytes=total,
            used_bytes=used,
            available_bytes=total - used,
            use_percent=use_percent,
        )
    ]


def _lan() -> NetworkInterface:
    return NetworkInterface(
        name="lan",
        up=True,
        proto="static",
        device="br-lan",
        mac="aa:bb:cc:dd:ee:01",
        link=True,
        addresses=[NetworkAddress(address="192.168.1.1", prefix=24, family="ipv4")],
    )


def _wan() -> NetworkInterface:
    return NetworkInterface(
        name="wan",
        up=True,
        proto="dhcp",
        device="eth0",
        mac="aa:bb:cc:dd:ee:02",
        link=True,
        addresses=[NetworkAddress(address="203.0.113.10", prefix=24, family="ipv4")],
    )


def _device(
    cpu: CpuInfo | None = None,
    memory: MemoryInfo | None = None,
    storage: list[StorageMount] | None = None,
    network: list[NetworkInterface] | None = None,
) -> DeviceSnapshot:
    return DeviceSnapshot(
        meta=_meta(),
        kernel=_kernel(),
        cpu=cpu,
        memory=memory,
        storage=storage or [],
        network=network or [],
        wifi=WifiInfo(radios=[WifiRadio(name="radio0", up=True, ssid="Home", station_count=2)]),
    )


def _healthy_snapshot() -> DeviceSnapshot:
    return _device(
        cpu=CpuInfo(
            load_1=0.8, load_5=0.7, load_15=0.6, cores=4, uptime_seconds=86400.0, usage_percent=20.0
        ),
        memory=_memory(40.0),
        storage=_storage(30.0),
    )


def _high_cpu_snapshot() -> DeviceSnapshot:
    return _device(
        cpu=CpuInfo(
            load_1=0.5, load_5=0.5, load_15=0.5, cores=4, uptime_seconds=86400.0, usage_percent=95.0
        ),
        memory=_memory(40.0),
        storage=_storage(30.0),
    )


def _high_memory_snapshot() -> DeviceSnapshot:
    return _device(
        cpu=CpuInfo(
            load_1=0.5, load_5=0.5, load_15=0.5, cores=4, uptime_seconds=86400.0, usage_percent=20.0
        ),
        memory=_memory(95.0),
        storage=_storage(30.0),
    )


def _missing_wan_snapshot() -> DeviceSnapshot:
    return _device(
        cpu=CpuInfo(
            load_1=0.5, load_5=0.5, load_15=0.5, cores=4, uptime_seconds=86400.0, usage_percent=20.0
        ),
        memory=_memory(40.0),
        storage=_storage(30.0),
        network=[_lan()],
    )


def _multi_finding_snapshot() -> DeviceSnapshot:
    return _device(
        cpu=CpuInfo(
            load_1=0.5, load_5=0.5, load_15=0.5, cores=4, uptime_seconds=86400.0, usage_percent=95.0
        ),
        memory=_memory(95.0),
        storage=_storage(96.0),
        network=[_lan()],
    )


# --------------------------------------------------------------------------- #
# Chat wiring (mirrors app.main with a mocked AI transport)                   #
# --------------------------------------------------------------------------- #


class _FakeSnapshotService:
    """Stand-in for the dashboard SnapshotService feeding RouterTool."""

    def __init__(self, update: DashboardUpdate | None) -> None:
        self._update = update

    def latest(self) -> DashboardUpdate | None:
        return self._update


class _CountingRouterTool(RouterTool):
    """RouterTool that records which section getters actually run."""

    def __init__(self, latest: Callable[[], DashboardUpdate | None], calls: list[str]) -> None:
        super().__init__(latest)
        self._calls = calls

    def get_system_info(self) -> dict[str, Any]:
        self._calls.append("system")
        return super().get_system_info()


def _router_update(snapshot: DeviceSnapshot) -> DashboardUpdate:
    return DashboardUpdate(
        type="update",
        sequence=1,
        sent_at=datetime.now(UTC),
        source="simulated",
        device_id="demo-router",
        connected=True,
        snapshot=snapshot,
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


def _register(
    router_manager: RouterManager,
    snapshot_service: _FakeSnapshotService,
    *,
    tool: RouterTool | None = None,
) -> None:
    router_manager.register("default", tool or RouterTool(snapshot_service.latest), default=True)


@contextmanager
def _chat_client(seen: dict, update: DashboardUpdate | None, *, tool: RouterTool | None = None):
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        snapshot_service = _FakeSnapshotService(update)
        router_manager = RouterManager()
        _register(router_manager, snapshot_service, tool=tool)
        app.state.snapshot_service = snapshot_service
        app.state.router_manager = router_manager
        app.state.chat_service = ChatService(
            _manager(seen),
            snapshot=lambda: update.snapshot if update is not None else None,
            router_manager=router_manager,
        )
        yield client


@contextmanager
def _status_client(update: DashboardUpdate | None):
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        snapshot_service = _FakeSnapshotService(update)
        router_manager = RouterManager()
        _register(router_manager, snapshot_service)
        app.state.snapshot_service = snapshot_service
        app.state.router_manager = router_manager
        yield client


def _sse_events(text: str) -> list[dict]:
    return [
        json.loads(raw.split("data:", 1)[1])
        for raw in text.split("\n\n")
        if raw.startswith("data:")
    ]


def _system_message(seen: dict) -> str:
    return seen["messages"][0]["content"]


# --------------------------------------------------------------------------- #
# Chat pipeline: healthy router                                               #
# --------------------------------------------------------------------------- #


def test_healthy_router_chat_injects_context_without_findings() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_healthy_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "e2e-healthy",
                "message": "show system, cpu, memory and storage",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello router"

    context = body["router_context"]
    assert context is not None
    assert "## Router" in context
    assert "- Hostname: demo-router" in context
    assert "## CPU" in context
    assert "## Memory" in context
    assert "## Storage" in context
    assert "## Network Interfaces" not in context
    assert "## Router Diagnosis" not in context
    assert "## Recommendations" not in context

    system = _system_message(seen)
    assert "### Router Context" in system
    assert "### End Router Context" in system
    assert "prefer factual values from it over model assumptions" in system


# --------------------------------------------------------------------------- #
# Chat pipeline: single-finding scenarios                                     #
# --------------------------------------------------------------------------- #


def test_high_cpu_chat_reports_finding_and_recommendation() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_high_cpu_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-cpu", "message": "show cpu usage"},
        )
    assert response.status_code == 200
    context = response.json()["router_context"]
    assert context is not None
    assert "## CPU" in context
    assert "## Router Diagnosis" in context
    assert "[CRITICAL] Critical CPU utilization" in context
    assert "## Recommendations" in context
    assert "[URGENT] Reduce CPU pressure" in context
    assert "Critical CPU utilization" in _system_message(seen)


def test_high_memory_chat_reports_finding_and_recommendation() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_high_memory_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-mem", "message": "show memory usage"},
        )
    assert response.status_code == 200
    context = response.json()["router_context"]
    assert context is not None
    assert "## Memory" in context
    assert "[CRITICAL] Critical memory utilization" in context
    assert "[URGENT] Optimize memory usage" in context


def test_missing_wan_chat_reports_wan_and_not_false_wifi() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_missing_wan_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-wan", "message": "show network interfaces"},
        )
    assert response.status_code == 200
    context = response.json()["router_context"]
    assert context is not None
    assert "## Network Interfaces" in context
    assert "[WARNING] Missing WAN interface" in context
    assert "[HIGH] Restore WAN connectivity" in context
    # The router has working WiFi and this network question does not collect
    # wifi data: it must NOT be diagnosed as missing.
    assert "Missing WiFi" not in context
    assert "Enable WiFi radios" not in context


def test_wifi_collected_and_absent_reports_missing_wifi() -> None:
    """When wifi data IS collected for the question and shows zero radios, the
    'Missing WiFi' finding legitimately appears."""
    from router_agent.model import WifiInfo

    snapshot = _missing_wan_snapshot()
    snapshot.wifi = WifiInfo(radios=[], networks=[])
    seen: dict = {}
    with _chat_client(seen, _router_update(snapshot)) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-wifi", "message": "show wireless clients"},
        )
    assert response.status_code == 200
    context = response.json()["router_context"]
    assert context is not None
    assert "[WARNING] Missing WiFi" in context


# --------------------------------------------------------------------------- #
# Chat pipeline: multiple findings                                            #
# --------------------------------------------------------------------------- #


def test_multiple_findings_chat_recommendations_priority_ordered() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_multi_finding_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "session_id": "e2e-multi",
                "message": "show system, cpu, memory, storage and network",
            },
        )
    assert response.status_code == 200
    context = response.json()["router_context"]
    assert context is not None

    for title in (
        "Critical CPU utilization",
        "Critical memory utilization",
        "Critical storage utilization",
        "Missing WAN interface",
    ):
        assert title in context
    # The snapshot has working WiFi; this question does not collect wifi, so it
    # must never be flagged as missing.
    assert "Missing WiFi" not in context

    recommendations = context.split("## Recommendations", 1)[1]
    titles = (
        "Reduce CPU pressure",
        "Optimize memory usage",
        "Free storage capacity",
        "Restore WAN connectivity",
    )
    positions = [recommendations.index(title) for title in titles]
    assert positions == sorted(positions)


# --------------------------------------------------------------------------- #
# Chat pipeline: intent detection and overrides                               #
# --------------------------------------------------------------------------- #


def test_non_router_conversation_skips_router_context() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_healthy_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-nr", "message": "hello there, how are you?"},
        )
    assert response.status_code == 200
    assert response.json()["router_context"] is None
    assert "### Router Context" not in _system_message(seen)
    assert "### End Router Context" not in _system_message(seen)


def test_router_aware_false_disables_context() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_high_cpu_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-off", "message": "show cpu usage", "router_aware": False},
        )
    assert response.status_code == 200
    assert response.json()["router_context"] is None
    assert "### Router Context" not in _system_message(seen)


def test_router_aware_true_with_non_router_message_skips_tool_layer() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_high_cpu_snapshot())) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-force", "message": "hello there", "router_aware": True},
        )
    assert response.status_code == 200
    assert response.json()["router_context"] is None


# --------------------------------------------------------------------------- #
# Chat pipeline: streaming                                                    #
# --------------------------------------------------------------------------- #


def test_streaming_chat_emits_router_context_once_on_done() -> None:
    seen: dict = {}
    with _chat_client(seen, _router_update(_high_cpu_snapshot())) as client:
        response = client.post(
            "/api/v1/chat/stream",
            json={"session_id": "e2e-stream", "message": "show cpu usage"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.text.count('"router_context"') == 1

    events = _sse_events(response.text)
    done = [event for event in events if event["type"] == "done"]
    deltas = [event["content"] for event in events if event["type"] == "delta"]
    assert len(done) == 1
    assert done[0]["router_context"] is not None
    assert "Critical CPU utilization" in done[0]["router_context"]
    assert done[0]["reply"] == "Hello router"
    assert deltas == ["Hello", " router"]
    assert all("router_context" not in event for event in events if event["type"] == "delta")

    system = _system_message(seen)
    assert "### Router Context" in system
    assert "Critical CPU utilization" in system


# --------------------------------------------------------------------------- #
# Chat pipeline: router unavailable / offline                                 #
# --------------------------------------------------------------------------- #


def test_chat_continues_when_router_unavailable() -> None:
    seen: dict = {}
    with _chat_client(seen, None) as client:
        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-una", "message": "show cpu usage", "router_aware": True},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["reply"] == "Hello router"
    assert body["router_context"] is None
    assert "### Router Context" not in _system_message(seen)


def test_offline_router_produces_connectivity_finding_and_recommendation() -> None:
    engine = RouterDiagnosisEngine()
    report = engine.diagnose(RouterSnapshot(), router_id="default")
    assert [finding.title for finding in report.findings] == ["Router is offline"]
    assert report.findings[0].severity == "critical"

    recommendations = RouterRecommendationEngine().generate(report)
    assert [(item.id, item.priority, item.title) for item in recommendations.recommendations] == [
        ("rec-connectivity", "urgent", "Restore router connectivity")
    ]
    markdown = recommendations.render_markdown()
    assert "[URGENT] Restore router connectivity" in markdown


# --------------------------------------------------------------------------- #
# Chat pipeline: cached router context                                        #
# --------------------------------------------------------------------------- #


def test_cached_router_context_reuses_executor_results() -> None:
    seen: dict = {}
    calls: list[str] = []
    update = _router_update(_healthy_snapshot())
    tool = _CountingRouterTool(lambda: update, calls)  # type: ignore[arg-type]
    with _chat_client(seen, update, tool=tool) as client:
        client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-cache", "message": "show system info"},
        )
        client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-cache", "message": "show hostname"},
        )
        cache = client.app.state.router_manager.default.cache
    assert calls == ["system"]
    assert cache.stats()["hits"] >= 1


# --------------------------------------------------------------------------- #
# Router status endpoint                                                      #
# --------------------------------------------------------------------------- #


def test_status_endpoint_healthy_router_full_pipeline() -> None:
    with _status_client(_router_update(_healthy_snapshot())) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["system"]["hostname"] == "demo-router"
    assert body["diagnosis"] == []
    assert body["recommendations"] == []
    assert body["connected"] is True
    assert body["sequence"] == 1
    assert body["error"] is None


def test_status_endpoint_high_cpu_reports_diagnosis_and_recommendation() -> None:
    with _status_client(_router_update(_high_cpu_snapshot())) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"]["cpu"]["usage_percent"] == 95.0
    assert [finding["title"] for finding in body["diagnosis"]] == ["Critical CPU utilization"]
    assert body["recommendations"][0]["id"] == "rec-cpu"
    assert body["recommendations"][0]["priority"] == "urgent"


def test_status_endpoint_unavailable_without_router() -> None:
    with _status_client(None) as client:
        response = client.get("/api/v1/router/status")
    assert response.status_code == 200
    body = response.json()
    assert body["snapshot"] is None
    assert body["diagnosis"] == []
    assert body["recommendations"] == []
    assert body["connected"] is False
    assert body["last_snapshot_at"] is None
    assert body["sequence"] == 0
    assert body["server_time"] is not None


# --------------------------------------------------------------------------- #
# RAG-enabled chat                                                            #
# --------------------------------------------------------------------------- #

_WIREGUARD_DOC = VectorDocument(
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

_FIREWALL_DOC = VectorDocument(
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


def _rag_handler(seen: dict[str, Any]):
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


def _rag_manager(seen: dict[str, Any]) -> ProviderManager:
    provider = make_provider(OpenAIProvider, _rag_handler(seen), name="rag", model="rag-m")
    return ProviderManager({"rag": provider}, default_provider="rag")


async def test_rag_chat_works_alongside_router_pipeline(tmp_path) -> None:
    from app.services.rag_service import RAGService
    from rag.ai import RAGConfiguration

    seen: dict[str, Any] = {}
    update = _router_update(_high_cpu_snapshot())
    manager = _rag_manager(seen)
    config = RAGConfiguration(
        collection="documents",
        top_k=4,
        max_documents=4,
        vector_dimensions=2,
        provider="rag",
        rerank_provider=None,
        rerank_model=None,
    )
    service = await RAGService.create(
        manager,
        config,
        vector_store_path=str(tmp_path / "vectors.sqlite3"),
    )
    await service._vector_store.add_documents(  # noqa: SLF001
        config.collection,
        [_WIREGUARD_DOC, _FIREWALL_DOC],
        namespace=config.namespace,
    )

    app = create_app()
    client = TestClient(app, headers=admin_headers())
    client.__enter__()
    try:
        snapshot_service = _FakeSnapshotService(update)
        router_manager = RouterManager()
        _register(router_manager, snapshot_service)
        client.app.state.snapshot_service = snapshot_service
        client.app.state.router_manager = router_manager
        client.app.state.chat_service = ChatService(
            service._manager,  # noqa: SLF001
            snapshot=lambda: update.snapshot,
            router_manager=router_manager,
        )
        client.app.state.rag_service = service

        response = client.post(
            "/api/v1/chat",
            json={"session_id": "e2e-rag", "message": "how does wireguard work?"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["rag"] is True
        assert body["reply"] == "Grounded answer [1]"
        assert len(body["citations"]) == 2

        context = client.app.state.chat_service.router_context_markdown("show cpu usage")
        assert context is not None
        assert "Critical CPU utilization" in context

        status = client.get("/api/v1/router/status")
        assert status.status_code == 200
        assert status.json()["snapshot"]["cpu"]["usage_percent"] == 95.0
    finally:
        client.__exit__(None, None, None)
        await service.aclose()
