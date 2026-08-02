"""PDF knowledge parser.

Extracts text page-by-page. Requires ``pypdf`` (the ``[pdf]`` extra); the
import is lazy and a clear :class:`KnowledgeParseError` is raised when the
library is missing, mirroring the FAISS backend's lazy-dependency pattern.
"""

from __future__ import annotations

from knowledge.errors import KnowledgeParseError
from knowledge.models import KnowledgeDocument
from knowledge.parsers._base import _document, _title
from knowledge.protocols import KnowledgeParser

try:
    import pypdf
except ImportError:  # pragma: no cover - exercised when pypdf is absent
    pypdf = None  # type: ignore[assignment]


class PdfParser(KnowledgeParser):
    """Parse PDF content into a :class:`KnowledgeDocument`."""

    format = "pdf"

    def parse(self, raw: bytes, *, reference: str = "", source: str = "") -> KnowledgeDocument:
        if pypdf is None:
            raise KnowledgeParseError(
                "The PDF parser requires 'pypdf'. "
                "Install it (e.g. pip install 'openwrt-ai-knowledge[pdf]')."
            )
        try:
            reader = pypdf.PdfReader(_BytesReader(raw))
            pages: list[str] = []
            for page in reader.pages:
                extracted = page.extract_text() or ""
                if extracted.strip():
                    pages.append(extracted)
        except Exception as exc:  # noqa: BLE001 - surface any pypdf failure uniformly
            raise KnowledgeParseError(f"Could not parse PDF {reference!r}: {exc}") from exc
        text = "\n\n".join(pages)
        return _document(
            self,
            text,
            reference=reference,
            source=source,
            title=_title(text),
        )


class _BytesReader:
    """Minimal file-like wrapper so ``pypdf.PdfReader`` accepts bytes."""

    def __init__(self, data: bytes) -> None:
        self._data = data
        self._position = 0

    def read(self, size: int = -1) -> bytes:
        if size < 0:
            data = self._data[self._position :]
            self._position = len(self._data)
            return data
        data = self._data[self._position : self._position + size]
        self._position += len(data)
        return data

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._position = offset
        elif whence == 1:
            self._position += offset
        elif whence == 2:
            self._position = len(self._data) + offset
        return self._position


__all__ = ["PdfParser"]
