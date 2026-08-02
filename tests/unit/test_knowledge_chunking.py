"""Chunking strategy tests for the knowledge platform."""

from __future__ import annotations

from knowledge.chunking import (
    FixedSizeChunkStrategy,
    HeadingChunkStrategy,
    ParagraphChunkStrategy,
    SlidingWindowChunkStrategy,
)
from knowledge.models import KnowledgeDocument, KnowledgeMetadata

_WORDS = [
    "the",
    "quick",
    "brown",
    "fox",
    "jumps",
    "over",
    "the",
    "lazy",
    "dog",
    "and",
    "runs",
    "far",
    "away",
    "through",
    "the",
    "forest",
    "towards",
    "the",
    "mountains",
    "under",
    "the",
    "stars",
]


def _doc(text: str, headings: list[dict] | None = None) -> KnowledgeDocument:
    return KnowledgeDocument(
        id="d1",
        text=text,
        metadata=KnowledgeMetadata(values={"headings": headings or []}),
    )


def test_fixed_size_chunks() -> None:
    text = " ".join(_WORDS)
    chunks = FixedSizeChunkStrategy(chunk_size=5).chunk(_doc(text))
    assert len(chunks) == 5  # 22 words / 5 = 5 chunks
    assert all(len(chunk.text.split()) <= 5 for chunk in chunks)
    assert [c.id for c in chunks] == [f"d1#{i}" for i in range(5)]
    assert chunks[0].document_id == "d1"
    assert chunks[0].heading == ""
    assert chunks[0].checksum


def test_fixed_size_deterministic_ids() -> None:
    text = " ".join(_WORDS)
    a = FixedSizeChunkStrategy(chunk_size=5).chunk(_doc(text))
    b = FixedSizeChunkStrategy(chunk_size=5).chunk(_doc(text))
    assert [c.text for c in a] == [c.text for c in b]
    assert [c.id for c in a] == [c.id for c in b]


def test_fixed_size_empty_text() -> None:
    assert FixedSizeChunkStrategy().chunk(_doc("")) == []


def test_fixed_size_chunk_size_at_least_one() -> None:
    strategy = FixedSizeChunkStrategy(chunk_size=-5)
    assert strategy.chunk_size == 1


def test_sliding_window_overlap_default() -> None:
    text = " ".join(_WORDS)
    chunks = SlidingWindowChunkStrategy(window_size=8).chunk(_doc(text))
    assert len(chunks) > 4  # overlapping windows produce more chunks than fixed
    first = chunks[0].text.split()
    second = chunks[1].text.split()
    assert first[-4:] == second[:4]  # default overlap = half window


def test_sliding_window_custom_overlap() -> None:
    text = " ".join(_WORDS)
    strategy = SlidingWindowChunkStrategy(window_size=10, overlap=2)
    chunks = strategy.chunk(_doc(text))
    first = chunks[0].text.split()
    second = chunks[1].text.split()
    assert first[-2:] == second[:2]
    assert strategy.overlap == 2


def test_sliding_window_overlap_not_negative() -> None:
    strategy = SlidingWindowChunkStrategy(window_size=5, overlap=-3)
    assert strategy.overlap == 0


def test_heading_chunk_splits_on_headings() -> None:
    text = "Intro section content\n\nDetails section content\n\nMore section content"
    headings = [
        {"text": "Intro section content", "level": 1, "offset": 0},
        {"text": "Details section content", "level": 2, "offset": 27},
        {"text": "More section content", "level": 1, "offset": 54},
    ]
    chunks = HeadingChunkStrategy(chunk_size=500).chunk(_doc(text, headings))
    assert len(chunks) == 3
    assert [c.heading for c in chunks] == [
        "Intro section content",
        "Details section content",
        "More section content",
    ]


def test_heading_chunk_falls_back_to_fixed_without_headings() -> None:
    text = " ".join(_WORDS)
    chunks = HeadingChunkStrategy(chunk_size=10).chunk(_doc(text, []))
    assert len(chunks) == 3  # 22 words / 10


def test_heading_chunk_re_splits_oversized_sections() -> None:
    text = "Section intro words.\n\n" + " ".join(_WORDS) + "\n\nTrailing."
    headings = [{"text": "Section intro words.", "level": 1, "offset": 0}]
    chunks = HeadingChunkStrategy(chunk_size=10).chunk(_doc(text, headings))
    assert len(chunks) == 3  # 26 words re-split into 3
    assert chunks[0].heading == "Section intro words."


def test_paragraph_chunk_splits_on_blank_lines() -> None:
    text = "One paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    chunks = ParagraphChunkStrategy(chunk_size=2).chunk(_doc(text))
    assert len(chunks) == 3
    assert chunks[1].text == "Second paragraph."


def test_paragraph_chunk_merges_short_adjacent() -> None:
    text = "Short.\n\nNext.\n\n" + " ".join(_WORDS)
    chunks = ParagraphChunkStrategy(chunk_size=20).chunk(_doc(text))
    assert chunks[0].text == "Short.\n\nNext."
    assert len(chunks) == 3  # merged pair + 28-word paragraph re-split into 2


def test_paragraph_chunk_empty() -> None:
    assert ParagraphChunkStrategy().chunk(_doc("")) == []


def test_chunk_ids_deterministic_across_strategies() -> None:
    text = " ".join(_WORDS)
    fixed = FixedSizeChunkStrategy(chunk_size=10).chunk(_doc(text))
    assert [c.id for c in fixed] == [f"d1#{i}" for i in range(len(fixed))]
