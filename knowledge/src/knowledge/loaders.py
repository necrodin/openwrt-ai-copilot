"""Knowledge loaders — fetch raw content for a reference.

A loader turns a reference (a file path, URL, or in-memory id) into raw bytes.
Loaders are format-agnostic; format handling is the parsers' job.

- :class:`TextLoader` — wraps in-memory text/bytes keyed by id.
- :class:`FileLoader` — reads a local file.
- :class:`DirectoryLoader` — reads files under a directory (matched by glob).
- :class:`HttpLoader` — fetches a URL via httpx (injectable client for tests).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from knowledge.errors import KnowledgeLoaderError
from knowledge.protocols import KnowledgeLoader


class TextLoader(KnowledgeLoader):
    """Serve pre-loaded text/bytes by an arbitrary id.

    ``documents`` maps a reference id to its content (str or bytes). Used for
    in-memory sources and tests.
    """

    loader_type = "text"

    def __init__(self, documents: dict[str, str | bytes] | None = None) -> None:
        self._documents = dict(documents or {})

    def add(self, reference: str, content: str | bytes) -> None:
        self._documents[reference] = content

    def load(self, reference: str) -> bytes:
        try:
            content = self._documents[reference]
        except KeyError as exc:
            message = f"No in-memory document for reference {reference!r}"
            raise KnowledgeLoaderError(message) from exc
        if isinstance(content, bytes):
            return content
        return content.encode("utf-8")


class FileLoader(KnowledgeLoader):
    """Read a local file's raw bytes."""

    loader_type = "file"

    def load(self, reference: str) -> bytes:
        path = Path(reference)
        try:
            return path.read_bytes()
        except OSError as exc:
            raise KnowledgeLoaderError(f"Could not read file {reference!r}: {exc}") from exc


class DirectoryLoader(KnowledgeLoader):
    """Read every file under a directory as ``<id> -> bytes``.

    ``pattern`` is a glob (e.g. ``"**/*.md"``) applied relative to ``root``.
    The reference used by the caller is the file's path relative to ``root``.
    """

    loader_type = "directory"

    def __init__(self, root: str | Path = "", pattern: str = "**/*") -> None:
        self._root = Path(root)
        self._pattern = pattern

    def references(self) -> list[str]:
        if not self._root.is_dir():
            return []
        matches = [path for path in self._root.glob(self._pattern) if path.is_file()]
        return sorted(str(path.relative_to(self._root)) for path in matches)

    def load(self, reference: str) -> bytes:
        path = Path(reference)
        if not path.is_absolute():
            path = self._root / path
        try:
            return path.read_bytes()
        except OSError as exc:
            raise KnowledgeLoaderError(f"Could not read file {reference!r}: {exc}") from exc


class HttpLoader(KnowledgeLoader):
    """Fetch a URL's raw bytes via httpx.

    An optional ``client`` (e.g. ``httpx.MockTransport``) can be injected for
    tests so nothing touches the network.
    """

    loader_type = "http"

    def __init__(
        self,
        *,
        client: Any | None = None,
        timeout_seconds: float = 30.0,
        headers: dict[str, str] | None = None,
    ) -> None:
        import httpx

        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(timeout_seconds),
            headers=headers or {},
            follow_redirects=True,
        )
        self._owns_client = client is None

    async def load_async(self, reference: str) -> bytes:
        import httpx

        try:
            response = await self._client.get(reference)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise KnowledgeLoaderError(f"HTTP load failed for {reference!r}: {exc}") from exc
        return response.content

    def load(self, reference: str) -> bytes:
        raise KnowledgeLoaderError("HttpLoader is async-only; use load_async")

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()


__all__ = ["DirectoryLoader", "FileLoader", "HttpLoader", "TextLoader"]
