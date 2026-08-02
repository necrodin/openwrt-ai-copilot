"""Chunk strategies for the knowledge platform.

Every strategy implements :class:`ChunkStrategy` and turns one
:class:`KnowledgeDocument` into :class:`KnowledgeChunk`\\ s. Chunk ids are
deterministic (``<document_id>#<index>``) so incremental indexing can diff
chunks across runs.

Strategies:

- :class:`FixedSizeChunkStrategy` — split by word count (no overlap).
- :class:`SlidingWindowChunkStrategy` — overlapping word windows.
- :class:`HeadingChunkStrategy` — split at heading boundaries (headings come
  from the parser via ``document.metadata["headings"]``); oversized sections
  are further split by word count. Falls back to fixed-size when no headings.
- :class:`ParagraphChunkStrategy` — split on paragraph (blank-line) boundaries;
  oversized paragraphs are further split by word count.

``chunk_size``/``overlap`` are configurable on every strategy; the defaults
match ``KnowledgeConfig``.
"""

from __future__ import annotations

import re

from knowledge.checksum import chunk_checksum
from knowledge.models import KnowledgeChunk, KnowledgeDocument
from knowledge.protocols import ChunkStrategy

_WORD_RE = re.compile(r"\S+")


def _words(text: str) -> list[str]:
    return _WORD_RE.findall(text)


def _make_chunks(
    document: KnowledgeDocument,
    texts: list[tuple[str, str]],
    *,
    strategy: str,
) -> list[KnowledgeChunk]:
    chunks: list[KnowledgeChunk] = []
    for index, (heading, text) in enumerate(texts):
        chunks.append(
            KnowledgeChunk(
                id=f"{document.id}#{index}",
                document_id=document.id,
                index=index,
                text=text,
                heading=heading,
                checksum=chunk_checksum(text),
            )
        )
    return chunks


class FixedSizeChunkStrategy(ChunkStrategy):
    """Split a document into fixed-size word chunks (no overlap)."""

    strategy_type = "fixed"

    def __init__(self, chunk_size: int = 500) -> None:
        self.chunk_size = max(1, int(chunk_size))

    def chunk(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        words = _words(document.text)
        if not words:
            return []
        texts: list[tuple[str, str]] = []
        for start in range(0, len(words), self.chunk_size):
            texts.append(("", " ".join(words[start : start + self.chunk_size])))
        return _make_chunks(document, texts, strategy=self.strategy_type)


class SlidingWindowChunkStrategy(ChunkStrategy):
    """Split a document into overlapping word windows.

    ``window_size`` is the words per window; ``overlap`` is how many words are
    shared between consecutive windows (defaults to half the window).
    """

    strategy_type = "sliding"

    def __init__(self, window_size: int = 500, overlap: int | None = None) -> None:
        self.window_size = max(1, int(window_size))
        self.overlap = max(0, int(overlap) if overlap is not None else self.window_size // 2)

    def chunk(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        words = _words(document.text)
        if not words:
            return []
        stride = max(1, self.window_size - self.overlap)
        texts: list[tuple[str, str]] = []
        start = 0
        while start < len(words):
            texts.append(("", " ".join(words[start : start + self.window_size])))
            if start + self.window_size >= len(words):
                break
            start += stride
        return _make_chunks(document, texts, strategy=self.strategy_type)


class HeadingChunkStrategy(ChunkStrategy):
    """Split a document at heading boundaries.

    Headings are read from ``document.metadata["headings"]`` — a list of
    ``{"text": str, "offset": int}`` records pointing into
    ``document.text``. Sections longer than ``chunk_size`` words are further
    split; when no headings exist the strategy falls back to fixed-size.
    """

    strategy_type = "heading"

    def __init__(self, chunk_size: int = 500) -> None:
        self.chunk_size = max(1, int(chunk_size))

    def chunk(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        headings = [
            {"text": str(entry.get("text", "")), "offset": int(entry.get("offset", 0))}
            for entry in (document.metadata.get("headings") or [])
            if isinstance(entry, dict)
        ]
        if not headings:
            return FixedSizeChunkStrategy(self.chunk_size).chunk(document)

        boundaries = sorted({0, *(heading["offset"] for heading in headings), len(document.text)})
        sections: list[tuple[str, str]] = []
        heading_by_offset = {heading["offset"]: heading["text"] for heading in headings}
        for index in range(len(boundaries) - 1):
            start, end = boundaries[index], boundaries[index + 1]
            section = document.text[start:end].strip()
            if not section:
                continue
            heading = heading_by_offset.get(start, "")
            if len(_words(section)) > self.chunk_size:
                words = _words(section)
                for word_start in range(0, len(words), self.chunk_size):
                    window = words[word_start : word_start + self.chunk_size]
                    sections.append((heading, " ".join(window)))
            else:
                sections.append((heading, section))
        return _make_chunks(document, sections, strategy=self.strategy_type)


class ParagraphChunkStrategy(ChunkStrategy):
    """Split a document on paragraph (blank-line) boundaries.

    Paragraphs longer than ``chunk_size`` words are further split; adjacent
    short paragraphs are merged to avoid one-word chunks.
    """

    strategy_type = "paragraph"

    def __init__(self, chunk_size: int = 500) -> None:
        self.chunk_size = max(1, int(chunk_size))

    def chunk(self, document: KnowledgeDocument) -> list[KnowledgeChunk]:
        paragraphs = [
            paragraph.strip() for paragraph in document.text.split("\n\n") if paragraph.strip()
        ]
        if not paragraphs:
            return []
        merged: list[str] = []
        buffer = ""
        for paragraph in paragraphs:
            if not buffer:
                buffer = paragraph
                continue
            if len(_words(buffer)) + len(_words(paragraph)) <= self.chunk_size:
                buffer = f"{buffer}\n\n{paragraph}"
            else:
                merged.append(buffer)
                buffer = paragraph
        if buffer:
            merged.append(buffer)

        texts: list[tuple[str, str]] = []
        for paragraph in merged:
            if len(_words(paragraph)) > self.chunk_size:
                words = _words(paragraph)
                for start in range(0, len(words), self.chunk_size):
                    texts.append(("", " ".join(words[start : start + self.chunk_size])))
            else:
                texts.append(("", paragraph))
        return _make_chunks(document, texts, strategy=self.strategy_type)


__all__ = [
    "FixedSizeChunkStrategy",
    "HeadingChunkStrategy",
    "ParagraphChunkStrategy",
    "SlidingWindowChunkStrategy",
]
