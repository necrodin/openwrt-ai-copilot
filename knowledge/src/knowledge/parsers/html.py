"""HTML knowledge parser.

Uses the standard library ``html.parser`` to walk a document, extracting the
``<title>``, heading tags (h1–h6, with offsets), and visible text. Script and
style blocks are skipped. Paragraph structure is preserved from ``<p>``,
``<li>``, and block-level tags so paragraph chunkers still work.
"""

from __future__ import annotations

from html.parser import HTMLParser

from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.parsers._base import _document, _title
from knowledge.protocols import KnowledgeParser

_BLOCK_TAGS = {
    "p",
    "div",
    "li",
    "ul",
    "ol",
    "section",
    "article",
    "header",
    "footer",
    "blockquote",
    "pre",
    "table",
    "tr",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "br",
}
_HEADING_TAGS = {"h1": 1, "h2": 2, "h3": 3, "h4": 4, "h5": 5, "h6": 6}
_SKIP_TAGS = {"script", "style", "noscript", "template", "head"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.headings: list[dict[str, str | int]] = []
        self.title: str = ""
        self._skip_depth = 0
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if tag == "title":
            self._in_title = True
        if tag == "p":
            self.parts.append("\n\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        if tag in _HEADING_TAGS:
            self.parts.append(f"\n{'#' * _HEADING_TAGS[tag]} ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if tag == "title":
            self._in_title = False
        if tag == "p":
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        if self._in_title:
            self.title = data.strip()
            return
        self.parts.append(data)

    def finish(self) -> tuple[str, list[dict[str, str | int]]]:
        text = "".join(self.parts)
        normalized, headings = _normalize_and_scan(text)
        return normalized, headings


def _normalize_and_scan(text: str) -> tuple[str, list[dict[str, str | int]]]:
    from knowledge.normalization import normalize_text

    normalized = normalize_text(text)
    headings: list[dict[str, str | int]] = []
    for line in normalized.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and not stripped.startswith("##"):
            heading = stripped.lstrip("#").strip()
            if heading:
                headings.append({"text": heading, "offset": normalized.find(stripped)})
    return normalized, headings


class HtmlParser(KnowledgeParser):
    """Parse HTML content into a :class:`KnowledgeDocument`."""

    format = "html"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        text = raw.decode("utf-8", errors="replace")
        extractor = _TextExtractor()
        extractor.feed(text)
        extractor.close()
        normalized, headings = extractor.finish()
        metadata = KnowledgeMetadata(values={"headings": headings})
        return _document(
            self,
            normalized,
            reference=reference,
            source=source,
            title=extractor.title or _title(normalized),
            metadata=metadata,
        )


__all__ = ["HtmlParser"]
