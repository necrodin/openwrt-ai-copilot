"""Router intent detector tests: router vs non-router classification."""

from __future__ import annotations

from app.services.router_intent_detector import RouterIntentDetector
from app.services.router_tool_registry import RouterToolRegistry
from app.services.router_tool_selector import RouterToolSelector


def _detector() -> RouterIntentDetector:
    registry = RouterToolRegistry()
    registry.register("system", lambda: {"hostname": "demo-router"})
    registry.register("cpu", lambda: {"usage_percent": 10})
    registry.register("memory", lambda: {"free_mb": 128})
    return RouterIntentDetector(RouterToolSelector(registry))


def test_classifies_router_requests() -> None:
    detector = _detector()
    assert detector.classify("show router system info") == "router"
    assert detector.classify("what is the cpu usage?") == "router"
    assert detector.classify("how much memory is free") == "router"


def test_classifies_non_router_requests() -> None:
    detector = _detector()
    assert detector.classify("hello there") == "non-router"
    assert detector.classify("what is 2 + 2?") == "non-router"
    assert detector.classify("thanks for your help") == "non-router"


def test_classify_reuses_selector_registry() -> None:
    registry = RouterToolRegistry()
    registry.register("system", lambda: {"hostname": "demo-router"})
    selector = RouterToolSelector(registry)
    detector = RouterIntentDetector(selector)
    assert detector.classify("show the hostname") == "router"
    assert detector.classify("tell me a joke") == "non-router"


def test_default_detector_no_registered_tools_classifies_non_router() -> None:
    detector = RouterIntentDetector()
    assert detector.classify("router uptime") == "non-router"
    assert detector.classify("hello") == "non-router"
