"""Citation generation for retrieved chunks.

One numbered :class:`Citation` is produced per source document, numbered by
first appearance in the ranked chunk list. The snippet is the first sentence of
the document's best chunk so citations stay meaningful even when the full chunk
text is later trimmed out of the prompt.
"""

from __future__ import annotations

import re

from rag.models import Citation, RetrievedChunk

_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_MAX_SNIPPET_CHARS = 160


class DefaultCitationBuilder:
    """Build numbered citations from a ranked chunk list."""

    def build(
        self,
        chunks: list[RetrievedChunk],
        *,
        max_snippet_chars: int = _MAX_SNIPPET_CHARS,
    ) -> list[Citation]:
        """Return one citation per document, ordered by first appearance."""
        by_document: dict[str, list[RetrievedChunk]] = {}
        order: list[str] = []
        for chunk in chunks:
            if chunk.document_id not in by_document:
                by_document[chunk.document_id] = []
                order.append(chunk.document_id)
            by_document[chunk.document_id].append(chunk)

        citations: list[Citation] = []
        for number, document_id in enumerate(order, start=1):
            doc_chunks = by_document[document_id]
            top = doc_chunks[0]
            citations.append(
                Citation(
                    number=number,
                    document_id=document_id,
                    chunk_ids=[chunk.id for chunk in doc_chunks],
                    source=top.metadata.get("source", ""),
                    reference=top.metadata.get("reference", ""),
                    title=top.metadata.get("title", ""),
                    format=top.metadata.get("format", ""),
                    snippet=self._snippet(top.text, max_snippet_chars),
                )
            )
        return citations

    @staticmethod
    def _snippet(text: str, max_chars: int) -> str:
        first = next(
            (piece.strip() for piece in _SENTENCE_BREAK.split(text or "") if piece.strip()),
            "",
        )
        if not first:
            return ""
        if len(first) <= max_chars:
            return first
        return first[: max_chars - 1].rstrip() + "…"


__all__ = ["DefaultCitationBuilder"]
