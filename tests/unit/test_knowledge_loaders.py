"""Loader tests for the knowledge platform."""

from __future__ import annotations

import pytest

from knowledge.errors import KnowledgeLoaderError
from knowledge.loaders import DirectoryLoader, FileLoader, HttpLoader, TextLoader


def test_text_loader_returns_bytes() -> None:
    loader = TextLoader({"a": "hello"})
    assert loader.load("a") == b"hello"


def test_text_loader_accepts_bytes() -> None:
    loader = TextLoader({"a": b"raw"})
    assert loader.load("a") == b"raw"


def test_text_loader_add_and_load() -> None:
    loader = TextLoader()
    loader.add("a", "content")
    assert loader.load("a") == b"content"


def test_text_loader_missing_raises() -> None:
    with pytest.raises(KnowledgeLoaderError, match="No in-memory document"):
        TextLoader().load("nope")


def test_file_loader(tmp_path) -> None:
    path = tmp_path / "a.txt"
    path.write_bytes(b"file bytes")
    assert FileLoader().load(str(path)) == b"file bytes"


def test_file_loader_missing_raises() -> None:
    with pytest.raises(KnowledgeLoaderError, match="Could not read file"):
        FileLoader().load("/does/not/exist.txt")


def test_directory_loader_references(tmp_path) -> None:
    (tmp_path / "a.md").write_text("a", encoding="utf-8")
    (tmp_path / "b.txt").write_text("b", encoding="utf-8")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / "c.md").write_text("c", encoding="utf-8")
    loader = DirectoryLoader(tmp_path, pattern="**/*.md")
    assert loader.references() == ["a.md", "sub/c.md"]


def test_directory_loader_missing_root_empty() -> None:
    assert DirectoryLoader("/does/not/exist").references() == []


def test_directory_loader_load(tmp_path) -> None:
    (tmp_path / "a.txt").write_text("content", encoding="utf-8")
    loader = DirectoryLoader(tmp_path)
    assert loader.load("a.txt") == b"content"


def test_http_loader_load_async() -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/docs"
        return httpx.Response(200, content=b"remote content")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    loader = HttpLoader(client=client)

    async def run() -> bytes:
        result = await loader.load_async("http://test/docs")
        await loader.aclose()
        return result

    import asyncio

    assert asyncio.run(run()) == b"remote content"


def test_http_loader_sync_raises() -> None:
    import httpx

    client = httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    loader = HttpLoader(client=client)
    with pytest.raises(KnowledgeLoaderError, match="async-only"):
        loader.load("http://test/x")


def test_http_loader_http_error_wrapped() -> None:
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"boom")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    loader = HttpLoader(client=client)

    async def run() -> None:
        with pytest.raises(KnowledgeLoaderError, match="HTTP load failed"):
            await loader.load_async("http://test/boom")

    import asyncio

    asyncio.run(run())


def test_http_loader_owns_client_by_default() -> None:
    loader = HttpLoader(timeout_seconds=5)
    assert loader._owns_client is True
