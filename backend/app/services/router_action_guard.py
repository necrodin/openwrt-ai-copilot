"""Router action guard: safety layer for router write operations.

Every requested router action is classified before any write-capable tool is
executed. Read-only actions are always allowed, potentially disruptive actions
require confirmation, and dangerous actions are denied outright. The guard is
purely declarative and deterministic — no LLM, no external APIs, no tool
execution.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["allow", "require_confirmation", "deny"]
Risk = Literal["low", "medium", "high", "critical"]

# Potentially disruptive actions: allowed only with explicit confirmation.
_DISRUPTIVE_ACTIONS = frozenset(
    {
        "reboot",
        "restart service",
        "reload firewall",
        "restart network",
        "wifi disable",
        "interface down",
    }
)

# Dangerous actions: always denied, never executed.
_DANGEROUS_ACTIONS = frozenset(
    {
        "factory reset",
        "firmware upgrade",
        "package removal",
        "delete configuration",
        "filesystem erase",
    }
)


@dataclass(frozen=True)
class ActionDecision:
    """Structured outcome of the guard for one router action."""

    decision: Decision
    risk: Risk
    reason: str
    confirmation_required: bool
    action_name: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision,
            "risk": self.risk,
            "reason": self.reason,
            "confirmation_required": self.confirmation_required,
            "action_name": self.action_name,
        }


class RouterActionGuard:
    """Evaluates router actions and returns an :class:`ActionDecision`."""

    def evaluate(self, action_name: str) -> ActionDecision:
        """Classify ``action_name`` into an allow/confirm/deny decision."""
        if action_name in _DANGEROUS_ACTIONS:
            return ActionDecision(
                decision="deny",
                risk="critical",
                reason=(f"Action '{action_name}' is dangerous and is always denied."),
                confirmation_required=False,
                action_name=action_name,
            )
        if action_name in _DISRUPTIVE_ACTIONS:
            return ActionDecision(
                decision="require_confirmation",
                risk="high",
                reason=(
                    f"Action '{action_name}' is potentially disruptive and requires confirmation."
                ),
                confirmation_required=True,
                action_name=action_name,
            )
        return ActionDecision(
            decision="allow",
            risk="low",
            reason=f"Action '{action_name}' is read-only and always allowed.",
            confirmation_required=False,
            action_name=action_name,
        )


__all__ = ["ActionDecision", "RouterActionGuard"]
