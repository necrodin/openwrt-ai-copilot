"""Helpers for vector store tests.

``make_store`` builds a backend from a pytest ``tmp_path``; the in-process
backends (sqlite, faiss) are used for the conformance suite, the HTTP backends
(qdrant, chroma) are exercised with ``httpx.MockTransport``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import httpx

from vectorstore.backends.chroma import ChromaVectorStore
from vectorstore.backends.faiss import FAISSVectorStore
from vectorstore.backends.qdrant import QdrantVectorStore
from vectorstore.backends.sqlite import SQLiteVectorStore
from vectorstore.config import VectorStoreConfig


def make_store(store_type: str, tmp_path: Path, **config_kwargs: Any):
    """Build a backend configured for the given temp directory."""
    config_kwargs["type"] = store_type
    if store_type in ("sqlite", "faiss"):
        config_kwargs["path"] = str(tmp_path / "store")
    if store_type == "faiss":
        config_kwargs["path"] = str(tmp_path / "faiss")
    config = VectorStoreConfig(**config_kwargs)
    return _CLASSES[store_type](config)


def make_http_store(
    store_type: str,
    handler: Any,
    **config_kwargs: Any,
):
    """Build an HTTP backend backed by a mock transport."""
    config_kwargs["type"] = store_type
    config = VectorStoreConfig(**config_kwargs)
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    cls = _CLASSES[store_type]
    return cls(config, client=client)


_CLASSES: dict[str, Any] = {
    "sqlite": SQLiteVectorStore,
    "faiss": FAISSVectorStore,
    "qdrant": QdrantVectorStore,
    "chroma": ChromaVectorStore,
}
