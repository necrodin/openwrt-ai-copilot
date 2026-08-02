"""FAISS vector store — in-process index with a JSON metadata sidecar.

Uses ``faiss-cpu`` + ``numpy`` (optional dependencies, imported lazily). Each
collection is one FAISS ``IndexFlatIP`` over L2-normalized vectors (so the
inner product equals the cosine similarity) plus a JSON sidecar holding
metadata, text, versions, and the position-to-id map.

Requires the ``[faiss]`` extra; construction raises a clear error when the
libraries are missing. Every index operation runs inside ``asyncio.to_thread``
so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vectorstore.backends._filters import matches, validate_filters
from vectorstore.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
    DocumentNotFoundError,
    VectorStoreError,
)
from vectorstore.models import (
    DEFAULT_NAMESPACE,
    DISTANCE_COSINE,
    CollectionInfo,
    CollectionStats,
    MetadataFilter,
    SearchRequest,
    SearchResult,
    VectorDocument,
    VectorMetadata,
)
from vectorstore.protocols import VectorStore

try:
    import faiss
    import numpy as np
except ImportError:  # pragma: no cover - exercised when faiss is absent
    faiss = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]

_SAFE = re.compile(r"[^a-zA-Z0-9._-]")


def _qname(namespace: str, name: str) -> str:
    return f"{_SAFE.sub('_', namespace)}__{_SAFE.sub('_', name)}"


def _normalize(vector: list[float]) -> np.ndarray:
    arr = np.asarray(vector, dtype=np.float32)
    norm = np.linalg.norm(arr)
    if norm == 0:
        return arr
    return arr / norm


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


class FAISSVectorStore(VectorStore):
    """FAISS-backed :class:`VectorStore` (in-process, offline)."""

    provider_type = "faiss"

    def __init__(self, config: Any, **_: Any) -> None:
        if faiss is None or np is None:
            raise VectorStoreError(
                "The FAISS backend requires 'faiss-cpu' and 'numpy'. "
                "Install them (e.g. pip install 'openwrt-ai-vectorstore[faiss]')."
            )
        self.name = config.effective_name()
        self.default_namespace = config.default_namespace or DEFAULT_NAMESPACE
        self._directory = Path(config.effective_path())
        self._directory.mkdir(parents=True, exist_ok=True)
        self._lock = asyncio.Lock()
        self._cached: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # Plumbing                                                           #
    # ------------------------------------------------------------------ #

    async def health(self) -> bool:
        return self._directory.exists()

    async def aclose(self) -> None:
        return None

    def _index_path(self, qn: str) -> Path:
        return self._directory / f"{qn}.index"

    def _meta_path(self, qn: str) -> Path:
        return self._directory / f"{qn}.json"

    def _load(self, qn: str) -> dict[str, Any] | None:
        if qn in self._cached:
            return self._cached[qn]
        meta_path = self._meta_path(qn)
        if not meta_path.exists():
            return None
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        data["index"] = faiss.read_index(str(self._index_path(qn)))  # type: ignore[union-attr]
        self._cached[qn] = data
        return data

    def _persist(self, qn: str, data: dict[str, Any]) -> None:
        index = data["index"]
        snapshot = {key: value for key, value in data.items() if key != "index"}
        faiss.write_index(index, str(self._index_path(qn)))  # type: ignore[union-attr]
        self._meta_path(qn).write_text(
            json.dumps(snapshot, separators=(",", ":")), encoding="utf-8"
        )

    def _rebuild_index(self, data: dict[str, Any]) -> None:
        dimension = int(data["dimension"])
        index = faiss.IndexFlatIP(dimension)  # type: ignore[union-attr]
        for doc_id in data["id_map"]:
            doc = data["docs"][doc_id]
            index.add(_normalize(doc["vector"]).reshape(1, -1))
        data["index"] = index

    async def _run(self, operation: Any, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            return await asyncio.to_thread(operation, *args, **kwargs)

    # ------------------------------------------------------------------ #
    # Collections                                                        #
    # ------------------------------------------------------------------ #

    async def create_collection(
        self,
        name: str,
        *,
        dimension: int,
        namespace: str | None = None,
        metadata: VectorMetadata | None = None,
    ) -> CollectionInfo:
        ns = namespace or self.default_namespace

        def create() -> CollectionInfo:
            qn = _qname(ns, name)
            if self._load(qn) is not None:
                raise CollectionExistsError(
                    f"Collection {name!r} already exists in namespace {ns!r}"
                )
            data = {
                "namespace": ns,
                "name": name,
                "dimension": dimension,
                "distance": DISTANCE_COSINE,
                "created_at": _utcnow(),
                "metadata": (metadata or VectorMetadata()).to_dict(),
                "id_map": [],
                "docs": {},
                "index": faiss.IndexFlatIP(dimension),  # type: ignore[union-attr]
            }
            self._persist(qn, data)
            return CollectionInfo(
                name=name,
                namespace=ns,
                dimension=dimension,
                distance=DISTANCE_COSINE,
                metadata=metadata or VectorMetadata(),
                version=1,
                document_count=0,
                created_at=datetime.fromisoformat(data["created_at"]),
            )

        return await self._run(create)

    async def delete_collection(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> None:
        ns = namespace or self.default_namespace

        def delete() -> None:
            qn = _qname(ns, name)
            if self._load(qn) is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            self._cached.pop(qn, None)
            self._index_path(qn).unlink(missing_ok=True)
            self._meta_path(qn).unlink(missing_ok=True)

        await self._run(delete)

    async def list_collections(
        self,
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[CollectionInfo]:
        def list_all() -> list[CollectionInfo]:
            infos: list[CollectionInfo] = []
            for meta_path in sorted(self._directory.glob("*.json")):
                qn = meta_path.stem
                if "__" not in qn:
                    continue
                ns, name = qn.rsplit("__", 1)
                if namespace is not None and ns != namespace:
                    continue
                data = json.loads(meta_path.read_text(encoding="utf-8"))
                infos.append(self._data_to_info(data))
            infos.sort(key=lambda entry: (entry.namespace, entry.name))
            start = max(0, offset)
            if limit is not None:
                return infos[start : start + max(0, limit)]
            return infos[start:]

        return await self._run(list_all)

    async def collection_info(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionInfo | None:
        ns = namespace or self.default_namespace

        def info() -> CollectionInfo | None:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                return None
            return self._data_to_info(data)

        return await self._run(info)

    async def stats(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionStats:
        ns = namespace or self.default_namespace

        def compute() -> CollectionStats:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            max_version = 0
            for doc in data["docs"].values():
                max_version = max(max_version, int(doc.get("version") or 1))
            return CollectionStats(
                name=name,
                namespace=ns,
                document_count=len(data["id_map"]),
                dimension=int(data["dimension"]),
                max_version=max_version,
                created_at=datetime.fromisoformat(data["created_at"]),
            )

        return await self._run(compute)

    def _data_to_info(self, data: dict[str, Any]) -> CollectionInfo:
        return CollectionInfo(
            name=data["name"],
            namespace=data["namespace"],
            dimension=int(data["dimension"]),
            distance=data["distance"],
            metadata=VectorMetadata(values=dict(data.get("metadata") or {})),
            version=1,
            document_count=len(data["id_map"]),
            created_at=datetime.fromisoformat(data["created_at"]),
        )

    # ------------------------------------------------------------------ #
    # Documents                                                          #
    # ------------------------------------------------------------------ #

    async def add_documents(
        self,
        name: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> list[str]:
        ns = namespace or self.default_namespace

        def add() -> list[str]:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            self._validate_dimension(data, documents)
            for doc in documents:
                if doc.id in data["docs"]:
                    raise VectorStoreError(
                        f"Document {doc.id!r} already exists in collection {name!r}; "
                        "use update_documents to replace"
                    )
            now = _utcnow()
            for doc in documents:
                data["docs"][doc.id] = self._record(doc, max(1, doc.version), now)
                data["id_map"].append(doc.id)
                data["index"].add(_normalize(doc.vector).reshape(1, -1))
            self._persist(qn, data)
            return [doc.id for doc in documents]

        return await self._run(add)

    async def update_documents(
        self,
        name: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> int:
        ns = namespace or self.default_namespace

        def update() -> int:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            self._validate_dimension(data, documents)
            now = _utcnow()
            changed = 0
            for doc in documents:
                existing = data["docs"].get(doc.id)
                version = (
                    int(existing["version"]) + 1 if existing is not None else max(1, doc.version)
                )
                if existing is None:
                    data["id_map"].append(doc.id)
                data["docs"][doc.id] = self._record(doc, version, now)
                changed += 1
            self._rebuild_index(data)
            self._persist(qn, data)
            return changed

        return await self._run(update)

    async def delete_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
        ns = namespace or self.default_namespace

        def delete() -> int:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            to_delete = {doc_id for doc_id in ids if doc_id in data["docs"]}
            if not to_delete:
                return 0
            for doc_id in to_delete:
                data["docs"].pop(doc_id)
            data["id_map"] = [doc_id for doc_id in data["id_map"] if doc_id not in to_delete]
            self._rebuild_index(data)
            self._persist(qn, data)
            return len(to_delete)

        return await self._run(delete)

    async def get_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> list[VectorDocument]:
        ns = namespace or self.default_namespace

        def get() -> list[VectorDocument]:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            return [
                self._document_from_record(doc_id, data["docs"][doc_id])
                for doc_id in ids
                if doc_id in data["docs"]
            ]

        return await self._run(get)

    # ------------------------------------------------------------------ #
    # Search                                                             #
    # ------------------------------------------------------------------ #

    async def search(
        self,
        name: str,
        request: SearchRequest,
        *,
        namespace: str | None = None,
    ) -> list[SearchResult]:
        ns = namespace or self.default_namespace
        validate_filters(request.filters)

        def run() -> list[SearchResult]:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            if len(request.query_vector) != int(data["dimension"]):
                raise DimensionMismatchError(
                    f"Query has {len(request.query_vector)} dimensions; "
                    f"collection {name!r} expects {data['dimension']}"
                )
            pool_size = max(1, request.top_k, request.offset + (request.limit or 0))
            count = len(data["id_map"])
            k = min(pool_size, max(1, count)) if count else 0
            scored: list[tuple[float, str]] = []
            if k:
                distances, indices = data["index"].search(
                    _normalize(request.query_vector).reshape(1, -1), k
                )
                for distance, position in zip(distances[0], indices[0], strict=True):
                    position = int(position)
                    if position < 0 or position >= count:
                        continue
                    scored.append((float(distance), data["id_map"][position]))
            scored.sort(key=lambda item: item[0], reverse=True)
            results: list[SearchResult] = []
            for score, doc_id in scored:
                record = data["docs"][doc_id]
                metadata = VectorMetadata(values=dict(record.get("metadata") or {}))
                if not matches(metadata.to_dict(), request.filters):
                    continue
                results.append(
                    SearchResult(
                        id=doc_id,
                        score=max(-1.0, min(1.0, score)),
                        text=str(record.get("text") or ""),
                        metadata=metadata,
                        vector=list(record["vector"]) if request.include_vectors else [],
                        version=int(record.get("version") or 1),
                    )
                )
            start = max(0, request.offset)
            if request.limit is not None:
                return results[start : start + max(0, request.limit)]
            return results[start:]

        return await self._run(run)

    async def filter_documents(
        self,
        name: str,
        filters: list[MetadataFilter],
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[VectorDocument]:
        ns = namespace or self.default_namespace
        validate_filters(filters)

        def run() -> list[VectorDocument]:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            matched = [
                self._document_from_record(doc_id, data["docs"][doc_id])
                for doc_id in data["id_map"]
                if matches((data["docs"][doc_id].get("metadata") or {}), filters)
            ]
            start = max(0, offset)
            if limit is not None:
                return matched[start : start + max(0, limit)]
            return matched[start:]

        return await self._run(run)

    # ------------------------------------------------------------------ #
    # Metadata                                                           #
    # ------------------------------------------------------------------ #

    async def set_metadata(
        self,
        name: str,
        id: str,
        metadata: VectorMetadata,
        *,
        namespace: str | None = None,
    ) -> None:
        ns = namespace or self.default_namespace

        def set_meta() -> None:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            if id not in data["docs"]:
                raise DocumentNotFoundError(f"Document {id!r} not found in collection {name!r}")
            data["docs"][id]["metadata"] = metadata.to_dict()
            data["docs"][id]["updated_at"] = _utcnow()
            self._persist(qn, data)

        await self._run(set_meta)

    async def get_metadata(
        self,
        name: str,
        id: str,
        *,
        namespace: str | None = None,
    ) -> VectorMetadata:
        ns = namespace or self.default_namespace

        def get_meta() -> VectorMetadata:
            qn = _qname(ns, name)
            data = self._load(qn)
            if data is None:
                raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
            if id not in data["docs"]:
                raise DocumentNotFoundError(f"Document {id!r} not found in collection {name!r}")
            return VectorMetadata(values=dict(data["docs"][id].get("metadata") or {}))

        return await self._run(get_meta)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _record(self, doc: VectorDocument, version: int, now: str) -> dict[str, Any]:
        return {
            "text": doc.text,
            "vector": doc.vector,
            "metadata": doc.metadata.to_dict(),
            "version": version,
            "created_at": now,
            "updated_at": now,
        }

    def _document_from_record(self, doc_id: str, record: dict[str, Any]) -> VectorDocument:
        return VectorDocument(
            id=doc_id,
            vector=list(record.get("vector") or []),
            text=str(record.get("text") or ""),
            metadata=VectorMetadata(values=dict(record.get("metadata") or {})),
            version=int(record.get("version") or 1),
        )

    def _validate_dimension(self, data: dict[str, Any], documents: list[VectorDocument]) -> None:
        dimension = int(data["dimension"])
        for doc in documents:
            if len(doc.vector) != dimension:
                raise DimensionMismatchError(
                    f"Document {doc.id!r} has {len(doc.vector)} dimensions; "
                    f"collection {data['name']!r} expects {dimension}"
                )


__all__ = ["FAISSVectorStore"]
