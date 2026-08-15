"""Token estimation and budget management.

Until a real tokenizer is wired in, tokens are estimated
deterministically with a ``chars / chars_per_token`` heuristic — the same
convention the ``providers`` package already uses (``estimate_tokens``), so
estimates stay consistent across layers.

The :class:`TokenBudgetManager` enforces the configured ceilings and answers
"does this fit?" questions; automatic reduction lives in the prompt optimizer.
"""

from __future__ import annotations

import math

from rag.config import TokenBudgetConfig
from rag.models import Message
from rag.protocols import TokenEstimator

DEFAULT_CHARS_PER_TOKEN = 4.0


class HeuristicTokenEstimator:
    """Deterministic token estimate: ``ceil(len(text) / chars_per_token)``.

    Mirrors ``providers.compat_provider.estimate_tokens`` (chars/4) so
    retrieval-side and provider-side accounting agree.
    """

    def __init__(self, chars_per_token: float = DEFAULT_CHARS_PER_TOKEN) -> None:
        if chars_per_token <= 0:
            raise ValueError("chars_per_token must be positive")
        self.chars_per_token = chars_per_token

    def estimate(self, text: str) -> int:
        if not text:
            return 0
        return max(1, math.ceil(len(text) / self.chars_per_token))

    def estimate_messages(self, messages: list[Message]) -> int:
        return sum(self.estimate(message.content) for message in messages)


class TokenBudgetManager:
    """Enforces the configured token ceilings for the retrieval pipeline."""

    def __init__(
        self,
        budget: TokenBudgetConfig | None = None,
        estimator: TokenEstimator | None = None,
    ) -> None:
        self.budget = budget or TokenBudgetConfig()
        self.estimator = estimator or HeuristicTokenEstimator()

    # ------------------------------------------------------------------ #
    # Estimation                                                         #
    # ------------------------------------------------------------------ #

    def estimate(self, text: str) -> int:
        return self.estimator.estimate(text)

    def estimate_messages(self, messages: list[Message]) -> int:
        return self.estimator.estimate_messages(messages)

    # ------------------------------------------------------------------ #
    # Budget queries                                                     #
    # ------------------------------------------------------------------ #

    def fits_context(self, token_count: int) -> bool:
        return token_count <= self.budget.max_context_tokens

    def fits_prompt(self, token_count: int) -> bool:
        return token_count <= self.budget.max_prompt_tokens

    def history_budget(self, reserved: int = 0) -> int:
        """Tokens available for history, capped at the configured maximum."""
        return max(
            0,
            min(
                self.budget.max_history_tokens,
                self.budget.max_prompt_tokens - reserved,
            ),
        )

    def context_budget_for_documents(self) -> int:
        """Tokens left in the context budget after history is accounted for."""
        return max(
            0,
            self.budget.max_context_tokens - self.budget.max_history_tokens,
        )


__all__ = [
    "DEFAULT_CHARS_PER_TOKEN",
    "HeuristicTokenEstimator",
    "TokenBudgetManager",
]
