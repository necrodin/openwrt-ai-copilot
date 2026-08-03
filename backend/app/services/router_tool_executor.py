"""Router Tool executor: orchestrates execution of Router Tool requests.

The executor resolves each requested tool through the
:class:`RouterToolRegistry`, runs the tools sequentially in request order,
collects structured results, and keeps going even when an individual tool fails.
Individual failures are captured in the result and never raised to the caller.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.router_action_guard import RouterActionGuard
from app.services.router_tool_registry import RouterToolRegistry


@dataclass
class RouterToolResult:
    """Structured outcome of one Router Tool execution."""

    name: str
    ok: bool
    result: Any = None
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
        }


class RouterToolExecutor:
    """Executes Router Tool requests sequentially against a registry."""

    def __init__(
        self,
        registry: RouterToolRegistry,
        guard: RouterActionGuard | None = None,
    ) -> None:
        self._registry = registry
        self._guard = guard if guard is not None else RouterActionGuard()

    def execute(self, requests: list[str]) -> list[RouterToolResult]:
        """Run each requested tool in order, collecting structured results.

        Each request is first evaluated by the :class:`RouterActionGuard`.
        Requests that are not allowed are not executed; the decision is
        recorded in the result instead of running the tool. Execution
        continues after any individual tool failure; the failure is recorded
        in that tool's result instead of raising.
        """
        results: list[RouterToolResult] = []
        for name in requests:
            results.append(self._execute_one(name))
        return results

    def _execute_one(self, name: str) -> RouterToolResult:
        decision = self._guard.evaluate(name)
        if decision.decision != "allow":
            return RouterToolResult(
                name=name,
                ok=False,
                result=decision.to_dict(),
                error=decision.reason,
            )
        try:
            tool = self._registry.resolve(name)
            value = tool()
            return RouterToolResult(name=name, ok=True, result=value)
        except Exception as exc:  # noqa: BLE001 - individual failures never raise
            return RouterToolResult(name=name, ok=False, error=str(exc))


__all__ = ["RouterToolExecutor", "RouterToolResult"]
