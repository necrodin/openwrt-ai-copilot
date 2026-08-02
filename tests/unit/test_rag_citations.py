"""Citation builder tests."""

from __future__ import annotations

from rag.citations import DefaultCitationBuilder
from rag.models import RetrievedChunk


def make_chunk(document_id: str, text: str, score: float, index: int = 0) -> RetrievedChunk:
    return RetrievedChunk(
        id=f"{document_id}#{index}",
        document_id=document_id,
        index=index,
        text=text,
        score=score,
        metadata={
            "source": "wiki",
            "reference": "ref",
            "title": f"T {document_id}",
            "format": "markdown",
        },
    )


def test_one_citation_per_document_in_first_appearance_order() -> None:
    chunks = [
        make_chunk("d2", "second document text.", 0.9, index=0),
        make_chunk("d1", "first document text.", 0.8, index=0),
        make_chunk("d2", "more from second.", 0.5, index=1),
    ]
    citations = DefaultCitationBuilder().build(chunks)
    assert [(c.number, c.document_id) for c in citations] == [(1, "d2"), (2, "d1")]
    assert citations[0].chunk_ids == ["d2#0", "d2#1"]


def test_snippet_is_first_sentence() -> None:
    chunk = make_chunk("d1", "The firewall zones control forwarding. And more detail follows.", 0.8)
    citations = DefaultCitationBuilder().build([chunk])
    assert citations[0].snippet == "The firewall zones control forwarding."


def test_snippet_truncated_when_too_long() -> None:
    chunk = make_chunk("d1", "word " * 100, 0.8)
    citations = DefaultCitationBuilder().build([chunk], max_snippet_chars=30)
    assert len(citations[0].snippet) <= 30


def test_metadata_propagated_to_citation() -> None:
    chunk = make_chunk("d1", "Some text.", 0.8)
    citation = DefaultCitationBuilder().build([chunk])[0]
    assert citation.source == "wiki"
    assert citation.reference == "ref"
    assert citation.title == "T d1"
    assert citation.format == "markdown"


def test_empty_chunks_yields_no_citations() -> None:
    assert DefaultCitationBuilder().build([]) == []
