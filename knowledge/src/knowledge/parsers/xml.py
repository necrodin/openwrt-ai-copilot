"""XML knowledge parser.

Walks an XML document with ``xml.etree.ElementTree``. Visible text is
collected from every element (depth-first), block boundaries are inserted
between element subtrees, and the document title is taken from the ``title``
element or the root tag. A trailing metadata map can be embedded as
``<metadata key="k">v</metadata>`` or ``<meta name="k">v</meta>`` elements.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET

from knowledge.errors import KnowledgeParseError
from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.parsers._base import _document, _title
from knowledge.protocols import KnowledgeParser

_BLOCK_TAGS = {
    "title",
    "p",
    "para",
    "li",
    "item",
    "section",
    "div",
    "chapter",
    "heading",
    "h1",
    "h2",
    "h3",
    "h4",
}
_TITLE_TAGS = {"title", "h1", "heading"}


class XmlParser(KnowledgeParser):
    """Parse XML content into a :class:`KnowledgeDocument`."""

    format = "xml"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        text = raw.decode("utf-8", errors="replace")
        try:
            root = ET.fromstring(text)
        except ET.ParseError as exc:
            raise KnowledgeParseError(f"Invalid XML: {exc}") from exc

        parts: list[str] = []
        metadata: dict[str, object] = {}
        title = ""

        for element in root.iter():
            tag = _local_tag(element.tag)
            if tag in _TITLE_TAGS and not title and element.text and element.text.strip():
                title = element.text.strip()
            if tag in ("metadata", "meta"):
                self._collect_meta(element, metadata)
                continue
            if element.text and element.text.strip():
                parts.append(element.text.strip())
            if tag in _BLOCK_TAGS:
                parts.append("\n\n")

        body = "\n".join(parts)
        meta = KnowledgeMetadata(values=metadata)
        return _document(
            self,
            body,
            reference=reference,
            source=source,
            title=title or _title(body),
            metadata=meta,
        )

    def _collect_meta(self, element: ET.Element, target: dict[str, object]) -> None:
        key = element.get("key") or element.get("name")
        if not key:
            return
        value: str | list[str] = ""
        if element.text and element.text.strip():
            value = element.text.strip()
        if element.get("list") == "true" and element.text:
            value = [item.strip() for item in element.text.split(",") if item.strip()]
        target[key] = value


def _local_tag(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[1]
    return tag


__all__ = ["XmlParser"]
