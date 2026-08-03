"""Router action guard tests: allow / require_confirmation / deny decisions."""

from __future__ import annotations

from app.services.router_action_guard import ActionDecision, RouterActionGuard

_DISRUPTIVE = [
    "reboot",
    "restart service",
    "reload firewall",
    "restart network",
    "wifi disable",
    "interface down",
]

_DANGEROUS = [
    "factory reset",
    "firmware upgrade",
    "package removal",
    "delete configuration",
    "filesystem erase",
]


def test_read_only_actions_are_allowed() -> None:
    for name in ["system", "cpu", "memory", "storage", "network", "unknown-read-tool"]:
        decision = RouterActionGuard().evaluate(name)
        assert isinstance(decision, ActionDecision)
        assert decision.decision == "allow"
        assert decision.risk == "low"
        assert decision.confirmation_required is False
        assert decision.action_name == name
        assert decision.reason


def test_disruptive_actions_require_confirmation() -> None:
    for name in _DISRUPTIVE:
        decision = RouterActionGuard().evaluate(name)
        assert decision.decision == "require_confirmation"
        assert decision.risk == "high"
        assert decision.confirmation_required is True
        assert decision.action_name == name


def test_dangerous_actions_are_denied() -> None:
    for name in _DANGEROUS:
        decision = RouterActionGuard().evaluate(name)
        assert decision.decision == "deny"
        assert decision.risk == "critical"
        assert decision.confirmation_required is False
        assert decision.action_name == name


def test_decision_to_dict() -> None:
    decision = RouterActionGuard().evaluate("reboot")
    assert decision.to_dict() == {
        "decision": "require_confirmation",
        "risk": "high",
        "reason": decision.reason,
        "confirmation_required": True,
        "action_name": "reboot",
    }


def test_decision_is_deterministic() -> None:
    guard = RouterActionGuard()
    for _ in range(3):
        assert (
            guard.evaluate("factory reset").to_dict() == guard.evaluate("factory reset").to_dict()
        )
