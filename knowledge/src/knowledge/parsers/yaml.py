"""YAML knowledge parser.

Leverages the same extraction logic as the JSON parser since YAML 1.2 is a
superset of the JSON data model. Requires ``pyyaml`` (a dependency of the
knowledge package).
"""

from __future__ import annotations

import json
from typing import Any

from knowledge.errors import KnowledgeParseError
from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.parsers._base import _document, _title
from knowledge.parsers.json import JsonParser
from knowledge.protocols import KnowledgeParser


class YamlParser(KnowledgeParser):
    """Parse YAML content into a :class:`KnowledgeDocument`."""

    format = "yaml"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        text = raw.decode("utf-8", errors="replace")
        try:
            import yaml
        except ImportError as exc:  # pragma: no cover - pyyaml is a hard dep
            raise KnowledgeParseError("YAML parsing requires 'pyyaml'") from exc

        data: Any = text
        try:
            data = yaml.safe_load(text)
        except yaml.YAMLError:
            data = text

        if data is None or isinstance(data, str):
            body = data if isinstance(data, str) else ""
            metadata = KnowledgeMetadata()
            return _document(
                self,
                body,
                reference=reference,
                source=source,
                title=metadata.get("title") or _title(body),
                metadata=metadata,
            )

        # Reuse the JSON extraction on the parsed structure.
        json_text = json.dumps(data, ensure_ascii=False)
        doc = JsonParser().parse(json_text.encode("utf-8"), reference=reference, source=source)
        return _document(
            self,
            doc.text,
            reference=reference,
            source=source,
            title=doc.metadata.get("title") or _title(doc.text),
            metadata=doc.metadata,
        )


__all__ = ["YamlParser"]
