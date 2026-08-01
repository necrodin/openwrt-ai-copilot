"""Minimal, provider-agnostic HTTP transport.

Wraps httpx and maps HTTP/network failures onto the ``ai.core`` error
hierarchy. No provider SDK is ever imported — all provider adapters talk to
plain HTTP endpoints through this class.

An optional ``client`` can be injected (e.g. an ``httpx.MockTransport``) to
test adapters without touching the network.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import httpx

from ai.core.errors import (
    AuthenticationError,
    ContextLengthExceededError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)

_CONTEXT_ERROR_MARKERS = (
    "context",
    "max_tokens",
    "token limit",
    "too many tokens",
    "sequence too long",
    "maximum context length",
)


def map_http_status(status_code: int, body: str = "") -> ProviderError:
    if status_code in (401, 403):
        return AuthenticationError(f"Provider authentication failed (HTTP {status_code})")
    if status_code == 429:
        return RateLimitError(f"Provider rate limit exceeded (HTTP {status_code})")
    if status_code in (400, 413) and any(
        marker in body.lower() for marker in _CONTEXT_ERROR_MARKERS
    ):
        return ContextLengthExceededError(
            f"Request exceeded the model context window (HTTP {status_code})"
        )
    if status_code >= 500 or status_code == 404:
        return ProviderUnavailableError(f"Provider returned HTTP {status_code}: {body[:200]}")
    return ProviderError(f"Provider returned HTTP {status_code}: {body[:200]}")


class ProviderTransport:
    """Async HTTP client with error normalization."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
        timeout_seconds: float = 60.0,
        verify_tls: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        headers: dict[str, str] = {"Accept": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        if extra_headers:
            headers.update(extra_headers)
        self._client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers=headers,
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify_tls,
        )
        if client is not None:
            # An injected client (e.g. tests) must still receive the base URL,
            # auth, and extra headers; a real client is built with them already.
            self._client.base_url = self.base_url
            self._client.headers.update(headers)
        self._owns_client = client is None

    async def get(self, path: str, *, params: dict[str, Any] | None = None) -> dict:
        return await self._request("GET", path, params=params)

    async def post_json(self, path: str, payload: dict[str, Any]) -> dict:
        return await self._request("POST", path, json=payload)

    async def post_ndjson(self, path: str, payload: dict[str, Any]) -> AsyncIterator[dict]:
        """POST and yield each NDJSON line decoded as a dict (Ollama streaming)."""
        try:
            async with self._client.stream("POST", path, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise map_http_status(response.status_code, body)
                async for line in response.aiter_lines():
                    if line.strip():
                        import json

                        yield json.loads(line)
        except httpx.HTTPError as exc:
            raise self._map_network_error(exc) from exc

    async def post_sse(self, path: str, payload: dict[str, Any]) -> AsyncIterator[str]:
        """POST and yield each SSE ``data:`` payload (OpenAI-compatible streaming)."""
        try:
            async with self._client.stream("POST", path, json=payload) as response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "replace")
                    raise map_http_status(response.status_code, body)
                data_lines: list[str] = []
                async for line in response.aiter_lines():
                    stripped = line.strip()
                    if stripped.startswith("data:"):
                        data_lines.append(stripped[len("data:") :].strip())
                    elif stripped == "" and data_lines:
                        yield "\n".join(data_lines)
                        data_lines = []
                    elif not stripped:
                        continue
                if data_lines:
                    yield "\n".join(data_lines)
        except httpx.HTTPError as exc:
            raise self._map_network_error(exc) from exc

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict:
        try:
            response = await self._client.request(method, path, params=params, json=json)
        except httpx.HTTPError as exc:
            raise self._map_network_error(exc) from exc

        if response.status_code >= 400:
            body = response.text or ""
            raise map_http_status(response.status_code, body)
        return response.json()

    @staticmethod
    def _map_network_error(exc: httpx.HTTPError) -> ProviderError:
        return ProviderUnavailableError(f"Provider unreachable: {exc!r}")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["ProviderTransport", "map_http_status"]
