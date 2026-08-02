"""Filesystem and in-memory knowledge sources."""

from __future__ import annotations

from pathlib import Path

from knowledge.errors import KnowledgeSourceError
from knowledge.protocols import KnowledgeSource


class FileSystemSource(KnowledgeSource):
    """A knowledge source rooted at a local directory.

    ``pattern`` is a glob (e.g. ``"**/*.md"``). References are file paths
    relative to ``root``; formats are inferred from file extensions.
    """

    source_type = "filesystem"

    _EXTENSION_FORMATS = {
        ".md": "markdown",
        ".markdown": "markdown",
        ".html": "html",
        ".htm": "html",
        ".pdf": "pdf",
        ".txt": "txt",
        ".text": "txt",
        ".json": "json",
        ".yaml": "yaml",
        ".yml": "yaml",
        ".xml": "xml",
    }

    def __init__(self, root: str | Path, pattern: str = "**/*") -> None:
        self._root = Path(root)
        self._pattern = pattern

    @property
    def id(self) -> str:
        return f"filesystem:{self._root}"

    @property
    def description(self) -> str:
        return f"Local filesystem source rooted at {self._root}"

    def list_documents(self) -> list[str]:
        if not self._root.is_dir():
            return []
        return sorted(
            str(path.relative_to(self._root))
            for path in self._root.glob(self._pattern)
            if path.is_file()
        )

    def format_for(self, reference: str) -> str:
        return self._EXTENSION_FORMATS.get(Path(reference).suffix.lower(), "txt")

    def load(self, reference: str) -> bytes:
        path = Path(reference)
        if not path.is_absolute():
            path = self._root / path
        try:
            return path.read_bytes()
        except OSError as exc:
            raise KnowledgeSourceError(f"Could not read {reference!r}: {exc}") from exc


class StaticSource(KnowledgeSource):
    """An in-memory knowledge source.

    ``documents`` maps a reference id to raw content (str or bytes). Useful for
    tests, small snippets, and embedding packaged knowledge.
    """

    source_type = "static"

    def __init__(
        self,
        source_id: str,
        documents: dict[str, str | bytes] | None = None,
        *,
        format: str = "txt",
        description: str = "",
    ) -> None:
        self._id = source_id
        self._documents = dict(documents or {})
        self._format = format
        self._description = description
        self.formats = {format}

    @property
    def id(self) -> str:
        return self._id

    @property
    def description(self) -> str:
        return self._description

    def list_documents(self) -> list[str]:
        return list(self._documents)

    def format_for(self, reference: str) -> str:
        return self._format

    def load(self, reference: str) -> bytes:
        try:
            content = self._documents[reference]
        except KeyError as exc:
            raise KnowledgeSourceError(f"Static source has no document {reference!r}") from exc
        if isinstance(content, bytes):
            return content
        return content.encode("utf-8")


__all__ = ["FileSystemSource", "StaticSource"]
