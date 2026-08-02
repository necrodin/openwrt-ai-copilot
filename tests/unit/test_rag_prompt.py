"""Prompt builder + optimizer tests."""

from __future__ import annotations

import pytest

from rag.citations import DefaultCitationBuilder
from rag.errors import ContextLimitError
from rag.models import Message, PromptContext, RetrievedChunk
from rag.prompt import DefaultPromptBuilder, DefaultPromptOptimizer


def make_context(*, n_chunks: int = 3, n_history: int = 0) -> PromptContext:
    chunks = [
        RetrievedChunk(
            id=f"d{i}#0",
            document_id=f"d{i}",
            index=0,
            text=f"chunk text number {i} " * 20,
            score=1.0 - i * 0.1,
            rank=i + 1,
        )
        for i in range(n_chunks)
    ]
    history = [
        Message(
            role="user" if i % 2 == 0 else "assistant",
            content=f"history turn {i} " * 10,
        )
        for i in range(n_history)
    ]
    citations = DefaultCitationBuilder().build(chunks)
    context = PromptContext(
        query="What is the answer?",
        chunks=chunks,
        history=history,
        language="en",
        citations=citations,
    )
    context.token_estimate = len("\n".join(c.text for c in chunks)) // 4
    return context


def test_build_message_layout() -> None:
    request = DefaultPromptBuilder().build(make_context(n_history=2))
    assert request.messages[0].role == "system"
    assert [m.role for m in request.messages[1:-1]] == ["user", "assistant"]
    assert request.messages[-1].role == "user"


def test_build_user_message_contains_context_and_question() -> None:
    request = DefaultPromptBuilder().build(make_context(n_chunks=1))
    user = request.messages[-1].content
    assert "Context:" in user
    assert "[1] chunk text number 0" in user
    assert "Question: What is the answer?" in user


def test_citation_markers_in_user_message() -> None:
    context = make_context(n_chunks=2)
    request = DefaultPromptBuilder().build(context)
    user = request.messages[-1].content
    assert "[1]" in user and "[2]" in user


def test_citation_instruction_in_system_when_citations_present() -> None:
    context = make_context(n_chunks=2)
    system = DefaultPromptBuilder().build(context).messages[0].content
    assert "Cite sources using [N] markers" in system


def test_custom_system_prompt_override() -> None:
    context = make_context(n_chunks=0)
    request = DefaultPromptBuilder(system_prompt="You are a network guru.").build(context)
    assert request.messages[0].content == "You are a network guru."


def test_custom_system_prompt_with_citations_appends_instruction() -> None:
    request = DefaultPromptBuilder(system_prompt="Be terse.").build(make_context(n_chunks=2))
    system = request.messages[0].content
    assert system.startswith("Be terse.")
    assert "Cite sources using [N] markers" in system


def test_checksum_is_deterministic() -> None:
    builder = DefaultPromptBuilder()
    first = builder.build(make_context())
    second = builder.build(make_context())
    assert first.checksum == second.checksum
    assert first.checksum != builder.build(make_context(n_chunks=2)).checksum


def test_max_tokens_and_token_estimate() -> None:
    builder = DefaultPromptBuilder(reserved_output_tokens=750)
    request = builder.build(make_context())
    assert request.max_tokens == 750
    assert request.token_estimate > 0


def test_optimizer_returns_request_when_already_fits() -> None:
    context = make_context(n_chunks=1)
    request = DefaultPromptBuilder().build(context)
    optimized = DefaultPromptOptimizer().optimize(request, 100_000)
    assert optimized is request


def test_optimizer_trims_chunks_then_history() -> None:
    context = make_context(n_chunks=4, n_history=6)
    request = DefaultPromptBuilder().build(context)
    optimized = DefaultPromptOptimizer().optimize(request, 100)
    assert optimized.token_estimate <= 100
    assert len(optimized.context.chunks) < len(request.context.chunks)


def test_optimizer_drops_context_block_when_required() -> None:
    context = make_context(n_chunks=4)
    request = DefaultPromptBuilder().build(context)
    optimized = DefaultPromptOptimizer().optimize(request, 60)
    assert optimized.context.chunks == []


def test_optimizer_raises_when_impossible() -> None:
    context = make_context(n_chunks=4)
    request = DefaultPromptBuilder().build(context)
    with pytest.raises(ContextLimitError):
        DefaultPromptOptimizer().optimize(request, 2)


def test_optimizer_raises_without_context() -> None:
    request = DefaultPromptBuilder().build(PromptContext(query="only a question", chunks=[]))
    request.token_estimate = 5000
    with pytest.raises(ContextLimitError):
        DefaultPromptOptimizer().optimize(request, 10)
