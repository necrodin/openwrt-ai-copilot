"""ubus access through a shell command runner.

OpenWrt's ``ubus`` tool prints JSON on stdout for ``ubus call <object>
<method>``. This client runs it through any :class:`CommandRunner` (SSH or
local) and decodes the result, so collectors get structured data no matter how
the device is reached.
"""

from __future__ import annotations

import json
from typing import Any

from router_agent.errors import UbusError
from router_agent.transport.base import CommandRunner, clean_output


class UbusClient:
    """Thin wrapper around ``ubus call`` via a command runner."""

    def __init__(self, runner: CommandRunner, *, timeout: float | None = None) -> None:
        self._runner = runner
        self._timeout = timeout

    def available(self) -> bool:
        try:
            output = self._runner.run("ubus list", timeout=self._timeout)
        except Exception:  # noqa: BLE001
            return False
        return "system" in output or bool(output.strip())

    def call(
        self, object_: str, method: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Run ``ubus call <object> <method> [params]`` and return the JSON dict."""
        command = f"ubus call {object_} {method}"
        if params:
            command += f" {json.dumps(params, separators=(',', ':'))}"
        try:
            output = self._runner.run(command, timeout=self._timeout)
        except Exception as exc:  # noqa: BLE001
            raise UbusError(f"ubus call {object_}.{method} failed: {exc}") from exc
        return self._decode(object_, method, output)

    def _decode(self, object_: str, method: str, output: str) -> dict[str, Any]:
        text = clean_output(output)
        if not text:
            raise UbusError(f"ubus call {object_}.{method} returned no output")
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            raise UbusError(
                f"ubus call {object_}.{method} returned non-JSON: {text[:200]}"
            ) from exc
