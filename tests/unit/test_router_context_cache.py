"""Router context cache tests: TTL, per-session scoping, failure exclusion, stats."""

from __future__ import annotations

import time

from app.services.router_context_cache import RouterContextCache
from app.services.router_tool_executor import RouterToolResult


def _ok(name: str = "system") -> RouterToolResult:
    return RouterToolResult(name=name, ok=True, result={"hostname": "demo-router"})


def _fail(name: str = "cpu") -> RouterToolResult:
    return RouterToolResult(name=name, ok=False, error="collector failed")


def test_set_and_get_returns_cached_result() -> None:
    cache = RouterContextCache()
    cache.set("s1", "system", _ok())
    result = cache.get("s1", "system")
    assert result is not None
    assert result.name == "system"
    assert result.ok is True
    assert result.result == {"hostname": "demo-router"}


def test_miss_returns_none_and_counts() -> None:
    cache = RouterContextCache()
    assert cache.get("s1", "system") is None
    stats = cache.stats()
    assert stats["hits"] == 0
    assert stats["misses"] == 1


def test_cache_is_scoped_per_session() -> None:
    cache = RouterContextCache()
    cache.set("s1", "system", _ok())
    assert cache.get("s1", "system") is not None
    assert cache.get("s2", "system") is None


def test_failed_executions_never_cached() -> None:
    cache = RouterContextCache()
    cache.set("s1", "cpu", _fail())
    assert cache.get("s1", "cpu") is None


def test_expired_entries_are_ignored() -> None:
    cache = RouterContextCache(ttl_seconds=0.01)
    cache.set("s1", "system", _ok())
    assert cache.get("s1", "system") is not None
    time.sleep(0.02)
    assert cache.get("s1", "system") is None


def test_stats_count_hits_and_misses() -> None:
    cache = RouterContextCache()
    cache.set("s1", "system", _ok())
    assert cache.get("s1", "system") is not None
    assert cache.get("s1", "missing") is None
    stats = cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


def test_clear_specific_session_only() -> None:
    cache = RouterContextCache()
    cache.set("s1", "system", _ok())
    cache.set("s2", "system", _ok())
    cache.clear("s1")
    assert cache.get("s1", "system") is None
    assert cache.get("s2", "system") is not None


def test_clear_all_sessions() -> None:
    cache = RouterContextCache()
    cache.set("s1", "system", _ok())
    cache.set("s2", "cpu", _ok("cpu"))
    cache.clear()
    assert cache.get("s1", "system") is None
    assert cache.get("s2", "cpu") is None
