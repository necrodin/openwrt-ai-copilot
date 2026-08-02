"""Plain-text knowledge parser (TXT)."""

from __future__ import annotations

from knowledge.models import KnowledgeDocument
from knowledge.parsers._base import _document, _title
from knowledge.protocols import KnowledgeParser


class TextParser(KnowledgeParser):
    """Parse plain text content into a :class:`KnowledgeDocument`."""

    format = "txt"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        text = raw.decode("utf-8", errors="replace")
        return _document(
            self,
            text,
            reference=reference,
            source=source,
            title=_title(text),
        )


__all__ = ["TextParser"]
