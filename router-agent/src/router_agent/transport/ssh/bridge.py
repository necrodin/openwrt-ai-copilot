"""A bridge that runs asyncio coroutines on a dedicated background thread.

The router agent's existing :class:`CommandRunner` contract is synchronous
(``run() -> str``), but the SSH layer is async-native so it can use asyncssh.
:class:`EventLoopBridge` gives a thread-safe ``run(coro)`` that executes the
coroutine on a private event loop and returns the result (or raises its
exception) in the calling thread.
"""

from __future__ import annotations

import asyncio
import threading
from collections.abc import Coroutine
from typing import Any, TypeVar

T = TypeVar("T")

__all__ = ["EventLoopBridge"]


class EventLoopBridge:
    """Owns one event loop running in a daemon thread."""

    def __init__(self) -> None:
        self._loop = asyncio.new_event_loop()
        self._ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run_loop, name="ssh-transport-loop", daemon=True
        )
        self._thread.start()
        self._ready.wait()

    def _run_loop(self) -> None:
        asyncio.set_event_loop(self._loop)
        self._ready.set()
        self._loop.run_forever()

    def run(self, coro: Coroutine[Any, Any, T]) -> T:
        """Schedule ``coro`` on the bridge loop and block for its result."""
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def close(self) -> None:
        """Stop the loop and join the thread (idempotent)."""
        if self._thread is None:
            return
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5.0)
        self._loop.close()
        self._thread = None
