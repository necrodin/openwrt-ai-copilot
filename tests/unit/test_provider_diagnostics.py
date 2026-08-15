"""Provider diagnostics tests: model-based connection test + model discovery.

The probes are exercised against a mocked HTTP transport so nothing real is
called: a successful test must prove the chat/completions path answered with
the configured model (via the same streaming contract the Copilot uses), and
failures must map to the stable categories.
"""

from __future__ import annotations

import json
from collections.abc import Callable

import httpx
import pytest

from ai.core.errors import (
    AuthenticationError,
    ProviderUnavailableError,
)
from app.services.provider_diagnostics import (
    TEST_PROMPT,
    categorize_failure,
)
from providers.config import ProviderConfig
from providers.factory import create_provider
from providers.transport import ProviderTransport
from tests.unit.providers_helpers import make_mock_client


def _cfg(**overrides) -> ProviderConfig:
    base = {
        "type": "openai",
        "name": "probe",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
    }
    base.update(overrides)
    return ProviderConfig(**base)


def _diag(cfg: ProviderConfig, handler: Callable[[httpx.Request], httpx.Response]):
    """Patch transport creation so probes hit a MockTransport, not the network."""
    from app.services import provider_diagnostics as diagnostics

    def fake_build(c: ProviderConfig):
        client = make_mock_client(handler)
        transport = ProviderTransport(base_url=c.effective_base_url(), client=client)
        return create_provider(c, transport=transport)

    diagnostics.create_provider = fake_build  # type: ignore[attr-defined]
    return diagnostics


def _sse_body(reply: str, model: str) -> str:
    """A minimal OpenAI-compatible SSE stream the mock transport can yield."""
    return (
        f'data: {{"model": "{model}", "choices": '
        f'[{{"delta": {{"content": "{reply}"}}, "finish_reason": null}}]}}\n\n'
        'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n'
        "data: [DONE]\n\n"
    )


def _chat_handler(reply: str = "OK", model: str | None = None) -> Callable:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            assert body["messages"][-1]["content"] == TEST_PROMPT
            resolved_model = model or body["model"]
            assert body["stream"] is True
            return httpx.Response(
                200,
                content=_sse_body(reply, resolved_model),
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(404)

    return handler


def _models_handler(ids: list[str]) -> Callable:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": i} for i in ids]})
        return httpx.Response(404)

    return handler


@pytest.mark.asyncio
async def test_chat_test_succeeds_with_configured_model() -> None:
    cfg = _cfg()
    diag = _diag(cfg, _chat_handler(reply="OK"))

    result = await diag.test_provider_chat(cfg)

    assert result["ok"] is True
    assert result["category"] == "ok"
    assert result["model"] == "gpt-4o-mini"
    assert result["reply"] == "OK"
    assert result["latency_ms"] >= 0


@pytest.mark.asyncio
async def test_chat_test_uses_the_streaming_contract() -> None:
    """The probe must exercise the same stream flag the Copilot sends.

    "Connection OK" must mean the live ``/chat/stream`` path works — not merely
    a non-streaming completion. The mock verifies ``stream: true`` on the wire.
    """
    cfg = _cfg()
    seen: dict[str, bool] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            seen["stream"] = body.get("stream")
            return httpx.Response(
                200,
                content=_sse_body("OK", body["model"]),
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(404)

    diag = _diag(cfg, handler)
    result = await diag.test_provider_chat(cfg)

    assert result["ok"] is True
    assert result["reply"] == "OK"
    assert seen["stream"] is True


@pytest.mark.asyncio
async def test_chat_test_requires_a_model() -> None:
    diag = _diag(_cfg(), _chat_handler())
    result = await diag.test_provider_chat(_cfg(model=""))
    assert result["ok"] is False
    assert result["category"] == "invalid_configuration"


@pytest.mark.asyncio
async def test_chat_test_auth_failure_category() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    diag = _diag(_cfg(), handler)
    result = await diag.test_provider_chat(_cfg())
    assert result["ok"] is False
    assert result["category"] == "authentication_failed"


@pytest.mark.asyncio
async def test_chat_test_model_not_found_category() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            400, json={"error": {"message": "The model 'gpt-4o' does not exist"}}
        )

    diag = _diag(_cfg(), handler)
    result = await diag.test_provider_chat(_cfg())
    assert result["ok"] is False
    assert result["category"] == "model_not_found"


@pytest.mark.asyncio
async def test_chat_test_endpoint_unreachable_category() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    diag = _diag(_cfg(), handler)
    result = await diag.test_provider_chat(_cfg())
    assert result["ok"] is False
    assert result["category"] == "endpoint_unreachable"


@pytest.mark.asyncio
async def test_chat_test_timeout_category() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timed out")

    diag = _diag(_cfg(), handler)
    result = await diag.test_provider_chat(_cfg())
    assert result["ok"] is False
    assert result["category"] == "timeout"


@pytest.mark.asyncio
async def test_chat_test_rate_limit_category() -> None:
    """A 429 must be reported as rate_limited, never as Connection OK."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "rate limit exceeded"}})

    diag = _diag(_cfg(), handler)
    result = await diag.test_provider_chat(_cfg())
    assert result["ok"] is False
    assert result["category"] == "rate_limited"
    assert "Connection OK" not in result["message"]


@pytest.mark.asyncio
async def test_discovery_lists_models() -> None:
    cfg = _cfg()
    diag = _diag(cfg, _models_handler(["gpt-4o", "gpt-4o-mini"]))
    result = await diag.discover_provider_models(cfg)
    assert result["ok"] is True
    assert [m["id"] for m in result["models"]] == ["gpt-4o", "gpt-4o-mini"]


@pytest.mark.asyncio
async def test_discovery_failure_is_categorized_not_raised() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    diag = _diag(_cfg(), handler)
    result = await diag.discover_provider_models(_cfg())
    assert result["ok"] is False
    assert result["category"] == "endpoint_unreachable"


def test_categorize_failure_stable_mapping() -> None:
    assert categorize_failure(AuthenticationError("nope")) == (
        "authentication_failed",
        "nope",
    )
    assert categorize_failure(ProviderUnavailableError("Provider unreachable: ReadTimeout('x')"))[
        0
    ] == "timeout"
    assert categorize_failure(
        ProviderUnavailableError("Provider returned HTTP 404: model 'x' does not exist")
    )[0] == "model_not_found"
