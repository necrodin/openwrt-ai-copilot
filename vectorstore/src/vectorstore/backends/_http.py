"""Minimal async HTTP client for the Chroma and Qdrant backends.

Maps network failures to :class:`VectorStoreConnectionError` and auth failures
to :class:`VectorStoreAuthError`. Other HTTP errors raise
:class:`VectorStoreHttpStatusError` carrying the status code so backends can
translate them (e.g. a 404 becomes a ``None``/``CollectionNotFoundError``). An
optional ``client`` can be injected (e.g. ``httpx.MockTransport``) to test the
backends without touching the network.
"""

from __future__ import annotations

from typing import Any

import httpx

from vectorstore.errors import (
    VectorStoreAuthError,
    VectorStoreConnectionError,
    VectorStoreError,
)


class VectorStoreHttpStatusError(VectorStoreError):
    """A non-2xx response; ``status_code`` is available to the backend."""

    def __init__(self, status_code: int, message: str) -> None:
        self.status_code = status_code
        super().__init__(message)


class VectorStoreHttpClient:
    """Async JSON-over-HTTP client with error normalization."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
        verify_tls: bool = True,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        merged_headers = {"Accept": "application/json"}
        if headers:
            merged_headers.update(headers)
        if api_key:
            merged_headers["api-key"] = api_key
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            headers=merged_headers,
            timeout=httpx.Timeout(timeout_seconds),
            verify=verify_tls,
        )
        if client is not None:
            self._client.base_url = base_url.rstrip("/")
            self._client.headers.update(merged_headers)
        self._owns_client = client is None

    async def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        try:
            response = await self._client.request(method, path, json=json, params=params)
        except httpx.HTTPError as exc:
            raise VectorStoreConnectionError(f"Vector store unreachable: {exc!r}") from exc

        if response.status_code in (401, 403):
            raise VectorStoreAuthError(
                f"Vector store authentication failed (HTTP {response.status_code})"
            )
        if response.status_code >= 400:
            raise VectorStoreHttpStatusError(
                response.status_code,
                f"Vector store returned HTTP {response.status_code}: {(response.text or '')[:200]}",
            )
        if response.status_code == 204 or response.content in (b"", b"null"):
            return None
        return response.json()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["VectorStoreHttpClient", "VectorStoreHttpStatusError"]
