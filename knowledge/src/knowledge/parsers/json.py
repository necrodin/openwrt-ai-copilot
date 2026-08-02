"""JSON knowledge parser.

Handles three shapes:

- ``{"text": "..."}`` or ``{"content": "..."}`` — the string is the body.
- ``{"title": "...", "sections": [...]}`` — sections are joined.
- Anything else — serialized back to JSON text (pretty-printed).

Every other top-level key is exposed as metadata.
"""

from __future__ import annotations

import json
from typing import Any

from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.parsers._base import _document, _title
from knowledge.protocols import KnowledgeParser


class JsonParser(KnowledgeParser):
    """Parse JSON content into a :class:`KnowledgeDocument`."""

    format = "json"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        text = raw.decode("utf-8", errors="replace")
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return _document(
                self,
                text,
                reference=reference,
                source=source,
                title=_title(text),
            )

        body, metadata = self._extract(data)
        return _document(
            self,
            body,
            reference=reference,
            source=source,
            title=metadata.get("title") or _title(body),
            metadata=metadata,
        )

    def _extract(self, data: Any) -> tuple[str, KnowledgeMetadata]:
        if isinstance(data, str):
            return data, KnowledgeMetadata()
        if not isinstance(data, dict):
            return json.dumps(data, indent=2, ensure_ascii=False), KnowledgeMetadata()

        values: dict[str, Any] = {}
        for key, value in data.items():
            if key in ("text", "content", "sections", "body"):
                continue
            values[key] = value

        parts: list[str] = []
        for key in ("text", "content", "body"):
            if key in data and isinstance(data[key], str):
                parts.append(data[key])
        if isinstance(data.get("sections"), list):
            for section in data["sections"]:
                if isinstance(section, str):
                    parts.append(section)
                elif isinstance(section, dict):
                    title = str(section.get("title", ""))
                    body = str(section.get("text") or section.get("content") or "")
                    parts.append(f"{title}\n{body}".strip())
        body = "\n\n".join(parts)
        if not body:
            body = json.dumps(data, indent=2, ensure_ascii=False)
        return body, KnowledgeMetadata(values=values)


__all__ = ["JsonParser"]
