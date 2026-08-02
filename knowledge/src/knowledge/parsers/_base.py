"""Base helpers shared by every format parser."""

from __future__ import annotations

from datetime import UTC, datetime

from knowledge.models import KnowledgeDocument, KnowledgeMetadata
from knowledge.protocols import KnowledgeParser


def _now() -> datetime:
    return datetime.now(UTC)


def _document(
    parser: KnowledgeParser,
    text: str,
    *,
    reference: str,
    source: str,
    title: str = "",
    metadata: KnowledgeMetadata | None = None,
) -> KnowledgeDocument:
    """Build a normalized document with source/format plumbing attached."""
    from knowledge.normalization import normalize_text

    normalized = normalize_text(text)
    meta = metadata or KnowledgeMetadata()
    meta = meta.merge(KnowledgeMetadata(values={"format": parser.format}))
    return KnowledgeDocument(
        id=_document_id(parser.format, reference, source),
        source=source,
        reference=reference,
        format=parser.format,
        title=title,
        text=normalized,
        language="",
        metadata=meta,
        created_at=_now(),
    )


def _document_id(format: str, reference: str, source: str) -> str:
    """Stable document id: ``<format>:<source>:<reference>`` (hashed)."""
    import hashlib

    raw = f"{format}:{source}:{reference}".encode()
    return hashlib.sha1(raw).hexdigest()[:16]


def _title(text: str) -> str:
    """Title = first non-empty line, trimmed to a sensible length."""
    for line in text.splitlines():
        line = line.strip().strip("#").strip()
        if line:
            return line[:200]
    return ""


__all__ = ["_document", "_document_id", "_now", "_title"]
