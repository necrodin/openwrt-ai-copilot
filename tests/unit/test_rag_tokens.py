"""Token estimation and budget tests for the Retrieval Core."""

from __future__ import annotations

import pytest

from rag.config import TokenBudgetConfig
from rag.models import Message
from rag.tokens import HeuristicTokenEstimator, TokenBudgetManager


def test_heuristic_estimator_default_chars_per_token() -> None:
    estimator = HeuristicTokenEstimator()
    assert estimator.estimate("x" * 8) == 2
    assert estimator.estimate("x" * 9) == 3
    assert estimator.estimate("") == 0


def test_heuristic_estimator_custom_chars_per_token() -> None:
    estimator = HeuristicTokenEstimator(chars_per_token=2.0)
    assert estimator.estimate("abcd") == 2


def test_heuristic_estimator_rejects_bad_ratio() -> None:
    with pytest.raises(ValueError):
        HeuristicTokenEstimator(chars_per_token=0)


def test_estimator_messages_sums() -> None:
    estimator = HeuristicTokenEstimator()
    messages = [Message(role="user", content="a" * 4), Message(role="assistant", content="b" * 8)]
    assert estimator.estimate_messages(messages) == 3


def test_budget_defaults() -> None:
    manager = TokenBudgetManager()
    assert manager.budget.max_context_tokens == 6000
    assert manager.budget.max_prompt_tokens == 4000


def test_budget_fits_checks() -> None:
    manager = TokenBudgetManager(TokenBudgetConfig(max_prompt_tokens=100, max_context_tokens=200))
    assert manager.fits_prompt(100)
    assert not manager.fits_prompt(101)
    assert manager.fits_context(200)
    assert not manager.fits_context(201)


def test_history_budget_capped_and_reserved() -> None:
    budget = TokenBudgetConfig(
        max_history_tokens=1500, max_prompt_tokens=2000, reserved_output_tokens=1000
    )
    manager = TokenBudgetManager(budget)
    assert manager.history_budget() == 1500
    assert manager.history_budget(reserved=500) == 1500
    assert manager.history_budget(reserved=1000) == 1000
    assert manager.history_budget(reserved=2000) == 0


def test_context_budget_for_documents() -> None:
    budget = TokenBudgetConfig(max_context_tokens=5000, max_history_tokens=1000)
    manager = TokenBudgetManager(budget)
    assert manager.context_budget_for_documents() == 4000
