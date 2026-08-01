"""Transport error-mapping and wire-protocol tests."""

from __future__ import annotations

import json

import httpx
import pytest

from ai.core.errors import (
    AuthenticationError,
    ContextLengthExceededError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from providers.transport import ProviderTransport, map_http_status
from tests.unit.providers_helpers import make_mock_client


def test_map_http_status_authentication() -> None:
    assert isinstance(map_http_status(401), AuthenticationError)
    assert isinstance(map_http_status(403), AuthenticationError)


def test_map_http_status_rate_limit() -> None:
    assert isinstance(map_http_status(429), RateLimitError)


def test_map_http_status_context_length() -> None:
    assert isinstance(
        map_http_status(400, "maximum context length is 8192"), ContextLengthExceededError
    )
    assert isinstance(map_http_status(413, "Too many tokens"), ContextLengthExceededError)


def test_map_http_status_unavailable() -> None:
    assert isinstance(map_http_status(503), ProviderUnavailableError)
    assert isinstance(map_http_status(500), ProviderUnavailableError)
    assert isinstance(map_http_status(404), ProviderUnavailableError)


def test_map_http_status_generic() -> None:
    assert isinstance(map_http_status(422), ProviderError)
    assert not isinstance(map_http_status(422), ProviderUnavailableError)


async def test_post_json_happy_path() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/v1/chat/completions"
        assert request.headers["authorization"] == "Bearer sk-test"
        return httpx.Response(200, json={"ok": True})

    client = make_mock_client(handler)
    transport = ProviderTransport(base_url="http://test/v1", api_key="sk-test", client=client)
    result = await transport.post_json("/chat/completions", {"x": 1})
    assert result == {"ok": True}
    await transport.aclose()


async def test_post_json_raises_authentication() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": "unauthorized"})

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    with pytest.raises(AuthenticationError):
        await transport.post_json("/chat/completions", {})


async def test_post_ndjson_yields_lines() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        body = "\n".join(json.dumps({"n": i}) for i in range(3)) + "\n"
        return httpx.Response(200, text=body)

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    events = [event async for event in transport.post_ndjson("/api/chat", {})]
    assert events == [{"n": 0}, {"n": 1}, {"n": 2}]


async def test_post_sse_yields_data_payloads() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        body = 'data: {"a":1}\n\ndata: {"a":2}\n\ndata: [DONE]\n\n'
        return httpx.Response(200, text=body)

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    events = [event async for event in transport.post_sse("/chat/completions", {})]
    assert events == ['{"a":1}', '{"a":2}', "[DONE]"]


async def test_network_error_maps_to_unavailable() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    transport = ProviderTransport(base_url="http://test/v1", client=make_mock_client(handler))
    with pytest.raises(ProviderUnavailableError):
        await transport.post_json("/chat/completions", {})
