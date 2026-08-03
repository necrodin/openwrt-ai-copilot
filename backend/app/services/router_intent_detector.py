"""Router intent detection: decide whether a chat request needs router tools.

Deterministic matching only — no LLM. Classification reuses the
:class:`RouterToolSelector` instead of duplicating keyword logic: a request is
``router`` when the selector finds at least one Router Tool intent, otherwise
``non-router`` and the pipeline skips Router Tool execution entirely.
"""

from __future__ import annotations

from typing import Literal

from app.services.router_tool_selector import RouterToolSelector

RouterIntent = Literal["router", "non-router"]


class RouterIntentDetector:
    """Classifies user requests as router-related or not."""

    def __init__(self, selector: RouterToolSelector | None = None) -> None:
        self._selector = selector if selector is not None else RouterToolSelector()

    def classify(self, message: str) -> RouterIntent:
        """Return ``router`` when the request needs router tools, else ``non-router``."""
        return "router" if self._selector.select(message) else "non-router"
