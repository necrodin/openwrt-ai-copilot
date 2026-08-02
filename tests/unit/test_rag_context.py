"""DefaultContextBuilder tests: grouping, caps, citations, history trimming."""

from __future__ import annotations

from rag.config import TokenBudgetConfig
from rag.context import DefaultContextBuilder
from rag.models import Message, RetrievedChunk


def make_chunk(document_id: str, index: int, text: str, score: float) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{document_id}#{index}",
        document_id=document_id,
        index=index,
        text=text,
        score=score,
        metadata={"title": f"Title {document_id}"},
    )


def make_chunks() -> list[RetrievedChunk]:
    return [
        make_chunk("d1", 0, "chunk a of d1", 0.9),
        make_chunk("d1", 1, "chunk b of d1", 0.4),
        make_chunk("d2", 0, "chunk a of d2", 0.8),
        make_chunk("d3", 0, "chunk a of d3", 0.7),
        make_chunk("d2", 1, "chunk b of d2", 0.5),
    ]


def test_build_groups_and_orders_documents() -> None:
    builder = DefaultContextBuilder()
    context = builder.build("q", make_chunks())
    assert [doc.document_id for doc in context.documents] == ["d1", "d2", "d3"]
    # chunks are grouped per document, documents ordered by best chunk score
    assert [chunk.id for chunk in context.chunks] == ["d1#0", "d1#1", "d2#0", "d2#1", "d3#0"]


def test_max_documents_cap() -> None:
    builder = DefaultContextBuilder(max_documents=2)
    context = builder.build("q", make_chunks())
    assert [doc.document_id for doc in context.documents] == ["d1", "d2"]


def test_max_chunks_per_document_cap() -> None:
    builder = DefaultContextBuilder(max_chunks_per_document=1)
    context = builder.build("q", make_chunks())
    assert [chunk.id for chunk in context.chunks] == ["d1#0", "d2#0", "d3#0"]


def test_citations_built_when_enabled() -> None:
    builder = DefaultContextBuilder()
    context = builder.build("q", make_chunks())
    numbers = [(c.number, c.document_id) for c in context.citations]
    assert numbers == [(1, "d1"), (2, "d2"), (3, "d3")]
    assert context.citations[0].chunk_ids == ["d1#0", "d1#1"]


def test_citations_disabled() -> None:
    builder = DefaultContextBuilder(include_citations=False)
    context = builder.build("q", make_chunks())
    assert context.citations == []


def test_history_trimmed_to_budget() -> None:
    builder = DefaultContextBuilder(token_budget=TokenBudgetConfig(max_history_tokens=20))
    history = [Message(role="user", content="a" * 100), Message(role="assistant", content="b" * 10)]
    context = builder.build("q", make_chunks(), history=history)
    assert context.history == [history[1]]
    assert context.token_estimate > 0


def test_empty_history_with_zero_budget() -> None:
    builder = DefaultContextBuilder(token_budget=TokenBudgetConfig(max_history_tokens=0))
    context = builder.build("q", make_chunks(), history=[Message(role="user", content="hello")])
    assert context.history == []


def test_language_and_system_prompt_passthrough() -> None:
    builder = DefaultContextBuilder()
    context = builder.build("q", make_chunks(), language="en", system_prompt="Be terse.")
    assert context.language == "en"
    assert context.system_prompt == "Be terse."
