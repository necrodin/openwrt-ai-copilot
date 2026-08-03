"""Router context cache: in-memory TTL cache for Router Tool execution results.

Caching avoids unnecessary repeated router queries during a conversation. Only
successful results are cached; failed executions are never stored. Entries are
keyed by conversation/session and expire after a configurable TTL (default 30
seconds); expired entries are automatically ignored (treated as misses). The
cache preserves the existing :class:`RouterToolResult` format and exposes
hit/miss statistics. No external dependencies.
"""

from __future__ import annotations

import threading
import time

from app.services.router_tool_executor import RouterToolResult


class RouterContextCache:
    """In-memory per-session TTL cache for Router Tool results."""

    def __init__(self, ttl_seconds: float = 30.0) -> None:
        self._ttl = ttl_seconds
        self._entries: dict[tuple[str, str], tuple[float, RouterToolResult]] = {}
        self._hits = 0
        self._misses = 0
        self._lock = threading.Lock()

    def get(self, session_id: str, name: str) -> RouterToolResult | None:
        """Return the cached result for ``name`` in ``session_id`` if valid.

        Expired entries are ignored (counted as misses) and pruned.
        """
        key = (session_id, name)
        with self._lock:
            entry = self._entries.get(key)
            if entry is None:
                self._misses += 1
                return None
            stored_at, result = entry
            if time.monotonic() - stored_at > self._ttl:
                del self._entries[key]
                self._misses += 1
                return None
            self._hits += 1
            return result

    def set(self, session_id: str, name: str, result: RouterToolResult) -> None:
        """Cache ``result`` under ``name`` in ``session_id``.

        Failed executions are never cached.
        """
        if not result.ok:
            return
        key = (session_id, name)
        with self._lock:
            self._entries[key] = (time.monotonic(), result)

    def stats(self) -> dict[str, int]:
        """Return cache hit/miss statistics."""
        with self._lock:
            return {"hits": self._hits, "misses": self._misses}

    def clear(self, session_id: str | None = None) -> None:
        """Remove cached entries for ``session_id`` (all sessions when omitted)."""
        with self._lock:
            if session_id is None:
                self._entries.clear()
            else:
                self._entries = {
                    (sid, name): entry
                    for (sid, name), entry in self._entries.items()
                    if sid != session_id
                }
