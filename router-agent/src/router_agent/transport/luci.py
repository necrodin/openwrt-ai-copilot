"""LuCI RPC client (HTTP JSON-RPC).

LuCI exposes an HTTP ``ubus`` interface at ``/ubus`` (default). It speaks
JSON-RPC 2.0: a ``session.login`` returns a session token that is passed as the
first param of subsequent ``call`` requests. This client lets the agent collect
from a router whose SSH access is disabled but whose web UI is reachable.
"""

from __future__ import annotations

from typing import Any

import httpx

from router_agent.errors import LuciRpcError

_NULL_SESSION = "00000000000000000000000000000000"


class LuciRpcClient:
    """JSON-RPC client for LuCI's ``ubus`` HTTP endpoint."""

    def __init__(
        self,
        base_url: str,
        *,
        username: str | None = None,
        password: str | None = None,
        path: str = "/ubus",
        timeout: float = 15.0,
        verify_tls: bool = True,
        client: httpx.Client | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._path = path
        self._username = username
        self._password = password
        self._session: str | None = None
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=timeout, verify=verify_tls
        )
        if client is not None:
            # An injected client (e.g. tests) must still resolve relative paths.
            self._client.base_url = self._base_url
        if username and password is not None:
            self.login(username, password)

    @property
    def session(self) -> str | None:
        return self._session

    def login(self, username: str, password: str) -> str:
        result = self._request(
            object_="session",
            method="login",
            params={"username": username, "password": password},
            session=_NULL_SESSION,
        )
        token = result.get("ubus_rpc_session")
        if not token:
            raise LuciRpcError("LuCI session.login returned no session token")
        self._session = str(token)
        return self._session

    def call(
        self, object_: str, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        return self._request(
            object_=object_,
            method=method,
            params=params or {},
            session=self._session,
        )

    def _request(
        self,
        *,
        object_: str,
        method: str,
        params: dict[str, Any],
        session: str | None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "call",
            "params": [session, object_, method, params],
        }
        try:
            response = self._client.post(self._path, json=payload)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise LuciRpcError(f"LuCI RPC {object_}.{method} failed: {exc}") from exc
        body = response.json()
        result = body.get("result")
        if not isinstance(result, list) or len(result) < 2:
            raise LuciRpcError(f"LuCI RPC {object_}.{method} returned malformed result")
        code, data = result[0], result[1]
        if code != 0:
            raise LuciRpcError(f"LuCI RPC {object_}.{method} error {code}: {data}")
        if not isinstance(data, dict):
            return {}
        return data

    def close(self) -> None:
        self._client.close()
