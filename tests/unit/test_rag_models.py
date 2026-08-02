"""Data model tests for the Retrieval Core."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.models import (
    Citation,
    ConversationState,
    MemorySnapshot,
    Message,
    PromptContext,
    PromptRequest,
    PromptResponse,
    RetrievedChunk,
    RetrievedDocument,
    TokenCounts,
)


def test_message_roles_validated() -> None:
    assert Message(role="user", content="hi").role == "user"
    assert Message(role="assistant", content="yo").role == "assistant"
    with pytest.raises(ValidationError):
        Message(role="robot", content="hi")


def test_message_token_estimate() -> None:
    assert Message(content="x" * 100).token_estimate == 25
    assert Message(content="").token_estimate == 1


def test_retrieved_chunk_defaults() -> None:
    chunk = RetrievedChunk(id="doc#2", document_id="doc", index=2, text="body")
    assert chunk.score == 0.0
    assert chunk.rank is None
    assert chunk.heading == ""
    assert chunk.metadata == {}


def test_retrieved_chunk_parse_id() -> None:
    parsed = RetrievedChunk.parse_id("doc123#4")
    assert parsed == ("doc123", 4)
    assert RetrievedChunk.parse_id("nohash") is None
    assert RetrievedChunk.parse_id("a#b") is None


def test_retrieved_document_aggregates() -> None:
    chunks = [RetrievedChunk(id="d#0", document_id="d", index=0, text="a")]
    doc = RetrievedDocument(document_id="d", title="t", chunks=chunks)
    assert doc.chunk_count == 1
    assert doc.best_score == 0.0


def test_citation_defaults() -> None:
    citation = Citation(number=1, document_id="d")
    assert citation.chunk_ids == []
    assert citation.snippet == ""


def test_prompt_context_token_estimate_defaults_zero() -> None:
    context = PromptContext(query="q")
    assert context.token_estimate == 0


def test_prompt_request_budget_check() -> None:
    request = PromptRequest(query="q", token_estimate=10)
    assert request.is_within_budget(20)
    assert not request.is_within_budget(5)


def test_prompt_request_ids_and_checksum_defaults() -> None:
    first = PromptRequest(query="q")
    second = PromptRequest(query="q")
    assert first.request_id != second.request_id
    assert first.checksum == ""


def test_token_counts_defaults() -> None:
    counts = TokenCounts()
    assert counts.prompt_tokens == 0
    assert counts.max_tokens == 0


def test_prompt_response_message_text() -> None:
    request = PromptRequest(
        query="q",
        messages=[Message(role="user", content="hello")],
    )
    response = PromptResponse(request_id="r1", query="q", prompt=request)
    assert response.message_text == "user: hello"


def test_conversation_state_defaults() -> None:
    state = ConversationState(conversation_id="c1")
    assert state.messages == []
    assert state.snapshots == []
    assert state.token_count == 0
    assert state.pending_turns == 0


def test_memory_snapshot_defaults() -> None:
    snapshot = MemorySnapshot(conversation_id="c1")
    assert snapshot.keywords == []
    assert snapshot.message_ids == []
    assert snapshot.token_count == 0
