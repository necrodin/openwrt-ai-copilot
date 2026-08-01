"""Provider capability registry.

A thread-safe registry mapping (capability, provider_name) to adapter classes
or factory callables. Concrete providers register themselves in later sprints;
the registry itself is provider-agnostic and contains zero AI logic.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any


class CapabilityRegistry:
    """Registry of provider implementations keyed by capability."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._entries: dict[str, dict[str, Callable[..., Any]]] = {}

    def register(
        self,
        capability: str,
        provider_name: str,
        factory: Callable[..., Any],
    ) -> None:
        with self._lock:
            self._entries.setdefault(capability, {})[provider_name] = factory

    def unregister(self, capability: str, provider_name: str) -> None:
        with self._lock:
            self._entries.get(capability, {}).pop(provider_name, None)

    def get(self, capability: str, provider_name: str) -> Callable[..., Any] | None:
        with self._lock:
            return self._entries.get(capability, {}).get(provider_name)

    def all(self, capability: str) -> list[str]:
        with self._lock:
            return sorted(self._entries.get(capability, {}))

    def capabilities(self, provider_name: str) -> set[str]:
        with self._lock:
            return {cap for cap, providers in self._entries.items() if provider_name in providers}

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()


registry = CapabilityRegistry()
