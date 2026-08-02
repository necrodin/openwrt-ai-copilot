"""Token usage accounting tests."""

from __future__ import annotations

import httpx

from ai.core.models import TokenUsage, Usage
from providers.compat_provider import estimate_tokens
from providers.openai import OpenAIProvider
from tests.unit.providers_helpers import make_provider


def test_merge_accumulates_by_capability() -> None:
    usage = TokenUsage()
    usage.merge("chat", Usage(prompt_tokens=10, completion_tokens=5))
    usage.merge("chat", Usage(prompt_tokens=2, completion_tokens=1))
    usage.merge("embeddings", Usage(prompt_tokens=7))

    assert usage.prompt_tokens == 19
    assert usage.completion_tokens == 6
    assert usage.calls == 3
    assert usage.total_tokens == 25
    assert usage.by_capability["chat"].prompt_tokens == 12
    assert usage.by_capability["embeddings"].prompt_tokens == 7


def test_add_error() -> None:
    usage = TokenUsage()
    usage.add_error()
    assert usage.errors == 1


def test_absorb_merges_totals_and_errors() -> None:
    left = TokenUsage()
    left.merge("chat", Usage(prompt_tokens=10, completion_tokens=5))
    left.add_error()
    right = TokenUsage()
    right.merge("embeddings", Usage(prompt_tokens=7))
    right.add_error()

    left.absorb(right)
    assert left.prompt_tokens == 17
    assert left.completion_tokens == 5
    assert left.total_tokens == 22
    assert left.calls == 2
    assert left.errors == 2
    assert left.by_capability["embeddings"].prompt_tokens == 7


def test_absorb_does_not_mutate_source() -> None:
    source = TokenUsage()
    source.merge("chat", Usage(prompt_tokens=3))
    target = TokenUsage()
    target.absorb(source)
    assert source.prompt_tokens == 3
    assert source.calls == 1
    assert target.prompt_tokens == 3


def test_token_usage_is_deep_copied_snapshot() -> None:
    provider = make_provider(OpenAIProvider, lambda _: httpx.Response(404), model="m")
    snapshot = provider.token_usage()
    snapshot.calls = 999
    snapshot.by_capability["chat"] = Usage(prompt_tokens=1)
    assert provider.token_usage().calls == 0
    assert provider.token_usage().by_capability == {}


def test_estimate_tokens() -> None:
    assert estimate_tokens("") == 1
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("a" * 40) == 10


def test_cost_accumulates() -> None:
    provider = make_provider(
        OpenAIProvider,
        lambda _: httpx.Response(404),
        model="m",
        cost_per_1k_prompt=10.0,
        cost_per_1k_completion=20.0,
    )
    provider._usage.merge("chat", Usage(prompt_tokens=1000, completion_tokens=500))
    provider._usage.cost_usd += provider._cost(Usage(prompt_tokens=1000, completion_tokens=500))
    assert provider.token_usage().cost_usd == 20.0
