"""Metadata extractors for the knowledge platform.

Each extractor implements :class:`MetadataExtractor` and derives a slice of
:class:`KnowledgeMetadata` from a document. :class:`CompositeMetadataExtractor`
applies a list of extractors in order (later extractors may override earlier
values). Built-in extractors:

- :class:`TitleExtractor` — from the first heading or first line.
- :class:`HeadingExtractor` — the list of headings found by the parser.
- :class:`LanguageExtractor` — detected language (see :mod:`knowledge.language`).
- :class:`SourceExtractor` — source id / reference / format plumbing.
- :class:`StatsExtractor` — word / character / line counts.
"""

from __future__ import annotations

import re

from knowledge.language import detect_language
from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.protocols import MetadataExtractor

_WORD_RE = re.compile(r"\S+")


class TitleExtractor(MetadataExtractor):
    """Extract a title from the first heading or the first line."""

    extractor_type = "title"

    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        title = document.title
        if not title:
            headings = document.metadata.get("headings") or []
            if headings:
                title = str(headings[0].get("text", ""))
        if not title:
            for line in document.text.splitlines():
                if line.strip():
                    title = line.strip()
                    break
        return KnowledgeMetadata(values={"title": title})


class HeadingExtractor(MetadataExtractor):
    """Preserve the parser's heading list on the document metadata."""

    extractor_type = "headings"

    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        return KnowledgeMetadata(values={"headings": list(document.metadata.get("headings") or [])})


class LanguageExtractor(MetadataExtractor):
    """Detect the document language using :func:`knowledge.language.detect_language`."""

    extractor_type = "language"

    def __init__(self) -> None:
        self.language = ""
        self.confidence = ""

    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        language = document.language or detect_language(document.text)
        return KnowledgeMetadata(values={"language": language})


class SourceExtractor(MetadataExtractor):
    """Attach source plumbing (source id, reference, format) as metadata."""

    extractor_type = "source"

    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        return KnowledgeMetadata(
            values={
                "source": document.source,
                "reference": document.reference,
                "format": document.format,
            }
        )


class StatsExtractor(MetadataExtractor):
    """Count words, characters, and lines for the document."""

    extractor_type = "stats"

    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        text = document.text
        return KnowledgeMetadata(
            values={
                "word_count": len(_WORD_RE.findall(text)),
                "char_count": len(text),
                "line_count": len(text.splitlines()),
            }
        )


class CompositeMetadataExtractor(MetadataExtractor):
    """Apply several extractors in order, merging their results."""

    extractor_type = "composite"

    def __init__(self, extractors: list[MetadataExtractor] | None = None) -> None:
        self._extractors = extractors or []

    def add(self, extractor: MetadataExtractor) -> CompositeMetadataExtractor:
        self._extractors.append(extractor)
        return self

    def extract(self, document: KnowledgeDocument) -> KnowledgeMetadata:
        merged = KnowledgeMetadata()
        for extractor in self._extractors:
            merged = merged.merge(extractor.extract(document))
        return merged


__all__ = [
    "CompositeMetadataExtractor",
    "HeadingExtractor",
    "LanguageExtractor",
    "SourceExtractor",
    "StatsExtractor",
    "TitleExtractor",
]
