"""Markdown knowledge parser.

Extracts headings (levels 1–6) with character offsets into the normalized
text (so heading chunkers can split), removes the leading YAML front-matter
block when present (exposing its keys as metadata), and strips common
inline/block markup from the extracted text.
"""

from __future__ import annotations

import re

from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.parsers._base import _document, _title
from knowledge.protocols import KnowledgeParser

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*```")
_IMG_RE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_EMPHASIS_RE = re.compile(r"(\*\*|__|\*|_|~~|`)+")
_FRONT_MATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.DOTALL)


class MarkdownParser(KnowledgeParser):
    """Parse Markdown content into a :class:`KnowledgeDocument`."""

    format = "markdown"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        text = raw.decode("utf-8", errors="replace")

        metadata = KnowledgeMetadata()
        match = _FRONT_MATTER_RE.match(text)
        if match:
            block = match.group(1)
            text = text[match.end() :]
            metadata = metadata.merge(self._front_matter(block))

        headings: list[dict[str, str | int]] = []
        lines: list[str] = []
        for line in text.splitlines():
            heading = _HEADING_RE.match(line)
            if heading:
                level = len(heading.group(1))
                heading_text = heading.group(2).strip()
                headings.append({"text": heading_text, "level": level})
                # Normalize the heading into a plain text line so offsets in the
                # document text align with what heading chunkers see.
                lines.append(heading_text)
            elif _FENCE_RE.match(line):
                lines.append("")
            else:
                lines.append(line)

        merged = "\n".join(lines)
        merged = _IMG_RE.sub(r"\1", merged)
        merged = _LINK_RE.sub(r"\1", merged)
        merged = _EMPHASIS_RE.sub("", merged)

        # Recompute offsets against the normalized text the chunkers consume.
        normalized_text = self._normalize_with_offsets(merged, headings)
        metadata = metadata.merge(KnowledgeMetadata(values={"headings": headings}))

        return _document(
            self,
            normalized_text,
            reference=reference,
            source=source,
            title=metadata.get("title") or _title(merged),
            metadata=metadata,
        )

    def _front_matter(self, block: str) -> KnowledgeMetadata:
        values: dict[str, object] = {}
        for raw_line in block.splitlines():
            if ":" not in raw_line:
                continue
            key, _, value = raw_line.partition(":")
            key = key.strip()
            if not key:
                continue
            values[key] = value.strip().strip("'\"")
        return KnowledgeMetadata(values=values)

    def _normalize_with_offsets(self, text: str, headings: list[dict[str, str | int]]) -> str:
        """Normalize text while updating heading offsets to the new text."""
        from knowledge.normalization import normalize_text

        normalized = normalize_text(text)
        if not headings:
            return normalized

        # Match each heading's text within the normalized text, in order, to
        # assign its char offset. Headings appear in order, so a sequential
        # search is both correct and cheap.
        cursor = 0
        for heading in headings:
            needle = str(heading["text"])
            index = normalized.find(needle, cursor)
            if index >= 0:
                heading["offset"] = index
                cursor = index + len(needle)
        return normalized


__all__ = ["MarkdownParser"]
