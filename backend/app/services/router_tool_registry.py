"""Router Tool registry: registration and resolution of Router Tools by name.

The registry is the single source of truth for available Router Tools. Tools are
registered under stable names and resolved by name; duplicate registrations are
rejected and unknown tools raise a clear error.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any


class DuplicateRouterToolError(Exception):
    """Raised when a Router Tool is registered under an already-used name."""


class UnknownRouterToolError(Exception):
    """Raised when a Router Tool name cannot be resolved."""


class RouterToolRegistry:
    """Registers and resolves Router Tools by name."""

    def __init__(self) -> None:
        self._tools: dict[str, Callable[[], Any]] = {}

    def register(self, name: str, tool: Callable[[], Any]) -> None:
        """Register ``tool`` under ``name`` (rejects duplicates)."""
        if name in self._tools:
            raise DuplicateRouterToolError(f"router tool '{name}' is already registered")
        self._tools[name] = tool

    def resolve(self, name: str) -> Callable[[], Any]:
        """Return the tool registered under ``name``.

        Raises :class:`UnknownRouterToolError` when ``name`` is not registered.
        """
        try:
            return self._tools[name]
        except KeyError as exc:
            raise UnknownRouterToolError(f"unknown router tool: {name}") from exc

    @property
    def available(self) -> list[str]:
        """Names of all registered Router Tools."""
        return list(self._tools)
