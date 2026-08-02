"""Qdrant vector store — thin HTTP REST adapter (no SDK).

Talks to the Qdrant REST API (``/collections``, ``/collections/{name}/points``)
through :class:`VectorStoreHttpClient`. Namespaces are encoded into the Qdrant
collection name (``<namespace>__<name>``, sanitized) because Qdrant has no
native namespaces. Document ids are arbitrary strings in this API; they are
mapped to stable UUIDs on the wire and the original id travels in the point
payload.

Filters are applied with the shared pure-Python matcher so every backend has
identical semantics.
"""

from __future__ import annotations

import re
import uuid
from datetime import UTC, datetime
from typing import Any

from vectorstore.backends._filters import matches, validate_filters
from vectorstore.backends._http import (
    VectorStoreHttpClient,
    VectorStoreHttpStatusError,
)
from vectorstore.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
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

_SAFE = re.compile(r"[^a-zA-Z0-9._-]")
_MARKER = "__vectorstore"


def _qname(namespace: str, name: str) -> str:
    return f"{_SAFE.sub('_', namespace)}__{_SAFE.sub('_', name)}"


def _point_id(namespace: str, collection: str, doc_id: str) -> str:
    return str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"openwrt-ai/{_qname(namespace, collection)}/{doc_id}",
        )
    )


def _collection_marker(namespace: str, name: str, dimension: int) -> dict[str, Any]:
    return {
        _MARKER: True,
        "namespace": namespace,
        "name": name,
        "dimension": dimension,
        "distance": DISTANCE_COSINE,
    }


class QdrantVectorStore(VectorStore):
    """Qdrant-backed :class:`VectorStore` over its REST API."""

    provider_type = "qdrant"

    def __init__(self, config: Any, *, client: Any | None = None) -> None:
        self.name = config.effective_name()
        self.default_namespace = config.default_namespace or DEFAULT_NAMESPACE
        self._http = VectorStoreHttpClient(
            base_url=config.effective_base_url(),
            api_key=None,
            headers=config.extra_headers,
            timeout_seconds=config.timeout_seconds,
            verify_tls=config.verify_tls,
            client=client,
        )

    async def health(self) -> bool:
        try:
            await self._http.request("GET", "/collections")
            return True
        except Exception:  # noqa: BLE001 - health must never raise
            return False

    async def aclose(self) -> None:
        await self._http.aclose()

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
        qn = _qname(ns, name)
        marker = _collection_marker(ns, name, dimension)
        marker["metadata"] = metadata.to_dict() if metadata else {}
        payload = {
            "vectors": {"size": dimension, "distance": "Cosine"},
            "metadata": marker,
        }
        try:
            await self._http.request("PUT", f"/collections/{qn}", json=payload)
        except VectorStoreHttpStatusError as exc:
            if exc.status_code == 409:
                raise CollectionExistsError(
                    f"Collection {name!r} already exists in namespace {ns!r}"
                ) from exc
            raise
        return CollectionInfo(
            name=name,
            namespace=ns,
            dimension=dimension,
            distance=DISTANCE_COSINE,
            metadata=metadata or VectorMetadata(),
            version=1,
            document_count=0,
            created_at=datetime.now(UTC),
        )

    async def delete_collection(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> None:
        ns = namespace or self.default_namespace
        qn = _qname(ns, name)
        if await self.collection_info(name, namespace=ns) is None:
            raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
        await self._http.request("DELETE", f"/collections/{qn}")

    async def list_collections(
        self,
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[CollectionInfo]:
        data = await self._http.request("GET", "/collections")
        names = [item["name"] for item in data["result"]["collections"]]
        infos: list[CollectionInfo] = []
        for qn in names:
            if "__" not in qn:
                continue
            ns, name = qn.rsplit("__", 1)
            raw = await self._raw_info(qn)
            if raw is None:
                continue
            marker = raw.get("metadata") or {}
            if not marker.get(_MARKER):
                continue
            if namespace is not None and ns != namespace:
                continue
            infos.append(self._raw_to_info(name, ns, raw, marker))
        infos.sort(key=lambda item: (item.namespace, item.name))
        start = max(0, offset)
        if limit is not None:
            return infos[start : start + max(0, limit)]
        return infos[start:]

    async def _raw_info(self, qn: str) -> dict[str, Any] | None:
        try:
            data = await self._http.request("GET", f"/collections/{qn}")
        except VectorStoreHttpStatusError as exc:
            if exc.status_code == 404:
                return None
            raise
        return data.get("result") or {}

    async def collection_info(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionInfo | None:
        ns = namespace or self.default_namespace
        qn = _qname(ns, name)
        raw = await self._raw_info(qn)
        if raw is None:
            return None
        marker = raw.get("metadata") or {}
        if not marker.get(_MARKER):
            return None
        return self._raw_to_info(name, ns, raw, marker)

    def _raw_to_info(
        self,
        name: str,
        ns: str,
        raw: dict[str, Any],
        marker: dict[str, Any],
    ) -> CollectionInfo:
        config = raw.get("config") or {}
        params = config.get("params") or {}
        vectors = params.get("vectors") or {}
        if isinstance(vectors, list):
            vectors = vectors[0] if vectors else {}
        dimension = int(vectors.get("size") or marker.get("dimension") or 0)
        created_at = raw.get("created_at")
        return CollectionInfo(
            name=name,
            namespace=ns,
            dimension=dimension,
            distance=DISTANCE_COSINE,
            metadata=VectorMetadata(values=dict(marker.get("metadata") or {})),
            version=1,
            document_count=int(raw.get("vectors_count") or 0),
            created_at=(
                datetime.fromisoformat(created_at.replace("Z", "+00:00")) if created_at else None
            ),
        )

    async def stats(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionStats:
        ns = namespace or self.default_namespace
        info = await self.collection_info(name, namespace=ns)
        if info is None:
            raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
        max_version = await self._max_version(info)
        return CollectionStats(
            name=name,
            namespace=ns,
            document_count=info.document_count,
            dimension=info.dimension,
            max_version=max_version,
            created_at=info.created_at,
        )

    async def _max_version(self, info: CollectionInfo) -> int:
        max_version = 0
        for point in await self._scroll_all(info, with_payload=True):
            version = int((point.get("payload") or {}).get("version") or 0)
            max_version = max(max_version, version)
        return max_version

    # ------------------------------------------------------------------ #
    # Documents                                                          #
    # ------------------------------------------------------------------ #

    async def _require_collection(self, ns: str, name: str) -> CollectionInfo:
        info = await self.collection_info(name, namespace=ns)
        if info is None:
            raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
        return info

    def _validate_dimension(self, info: CollectionInfo, documents: list[VectorDocument]) -> None:
        for doc in documents:
            if len(doc.vector) != info.dimension:
                raise DimensionMismatchError(
                    f"Document {doc.id!r} has {len(doc.vector)} dimensions; "
                    f"collection {info.name!r} expects {info.dimension}"
                )

    def _payload(self, doc: VectorDocument, version: int) -> dict[str, Any]:
        return {
            "_id": doc.id,
            "text": doc.text,
            "metadata": doc.metadata.to_dict(),
            "version": version,
        }

    async def add_documents(
        self,
        name: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> list[str]:
        ns = namespace or self.default_namespace
        info = await self._require_collection(ns, name)
        self._validate_dimension(info, documents)
        if not documents:
            return []
        qn = _qname(ns, name)
        existing = await self._retrieve_points(qn, [doc.id for doc in documents], ns, name)
        if existing:
            raise VectorStoreError(
                f"One or more document ids already exist in collection {name!r}; "
                "use update_documents to replace"
            )
        points = [
            {
                "id": _point_id(ns, name, doc.id),
                "vector": doc.vector,
                "payload": self._payload(doc, max(1, doc.version)),
            }
            for doc in documents
        ]
        await self._http.request(
            "PUT", f"/collections/{qn}/points", json={"points": points}, params={"wait": "true"}
        )
        return [doc.id for doc in documents]

    async def update_documents(
        self,
        name: str,
        documents: list[VectorDocument],
        *,
        namespace: str | None = None,
    ) -> int:
        ns = namespace or self.default_namespace
        info = await self._require_collection(ns, name)
        self._validate_dimension(info, documents)
        if not documents:
            return 0
        qn = _qname(ns, name)
        existing_versions: dict[str, int] = {}
        for point in await self._retrieve_points(qn, [doc.id for doc in documents], ns, name):
            payload = point.get("payload") or {}
            existing_versions[payload.get("_id", "")] = int(payload.get("version") or 0)
        points = []
        for doc in documents:
            version = (
                existing_versions.get(doc.id, 0) + 1
                if doc.id in existing_versions
                else max(1, doc.version)
            )
            points.append(
                {
                    "id": _point_id(ns, name, doc.id),
                    "vector": doc.vector,
                    "payload": self._payload(doc, version),
                }
            )
        await self._http.request(
            "PUT", f"/collections/{qn}/points", json={"points": points}, params={"wait": "true"}
        )
        return len(points)

    async def delete_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
        ns = namespace or self.default_namespace
        await self._require_collection(ns, name)
        if not ids:
            return 0
        qn = _qname(ns, name)
        existing = await self._retrieve_points(qn, ids, ns, name)
        if not existing:
            return 0
        await self._http.request(
            "POST",
            f"/collections/{qn}/points/delete",
            json={"points": [point["id"] for point in existing]},
            params={"wait": "true"},
        )
        return len(existing)

    async def get_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> list[VectorDocument]:
        ns = namespace or self.default_namespace
        await self._require_collection(ns, name)
        if not ids:
            return []
        qn = _qname(ns, name)
        points = await self._retrieve_points(qn, ids, ns, name, with_vector=True)
        by_id = {
            point.get("payload", {}).get("_id"): self._point_to_document(point) for point in points
        }
        return [by_id[doc_id] for doc_id in ids if doc_id in by_id]

    async def _retrieve_points(
        self,
        qn: str,
        ids: list[str],
        ns: str,
        name: str,
        *,
        with_vector: bool = False,
    ) -> list[dict[str, Any]]:
        point_ids = [_point_id(ns, name, doc_id) for doc_id in ids]
        data = await self._http.request(
            "POST",
            f"/collections/{qn}/points",
            json={"ids": point_ids, "with_payload": True, "with_vector": with_vector},
        )
        return data.get("result") or []

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
        info = await self._require_collection(ns, name)
        if len(request.query_vector) != info.dimension:
            raise DimensionMismatchError(
                f"Query has {len(request.query_vector)} dimensions; "
                f"collection {name!r} expects {info.dimension}"
            )
        qn = _qname(ns, name)
        pool_size = max(request.top_k, request.offset + (request.limit or 0))
        data = await self._http.request(
            "POST",
            f"/collections/{qn}/points/search",
            json={
                "vector": request.query_vector,
                "limit": pool_size,
                "with_payload": True,
                "with_vector": request.include_vectors,
            },
            params={"wait": "true"},
        )
        results: list[SearchResult] = []
        for item in data.get("result") or []:
            payload = item.get("payload") or {}
            metadata = VectorMetadata(values=dict(payload.get("metadata") or {}))
            if not matches(metadata.to_dict(), request.filters):
                continue
            results.append(
                SearchResult(
                    id=payload.get("_id", ""),
                    score=float(item.get("score") or 0.0),
                    text=str(payload.get("text") or ""),
                    metadata=metadata,
                    vector=list(item.get("vector") or []) if request.include_vectors else [],
                    version=int(payload.get("version") or 1),
                )
            )
        results.sort(key=lambda item: item.score, reverse=True)
        start = max(0, request.offset)
        if request.limit is not None:
            return results[start : start + max(0, request.limit)]
        return results[start:]

    async def filter_documents(
        self,
        name: str,
        filters: list[MetadataFilter],
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[VectorDocument]:
        validate_filters(filters)
        ns = namespace or self.default_namespace
        info = await self._require_collection(ns, name)
        matched: list[VectorDocument] = []
        for point in await self._scroll_all(info, with_payload=True, with_vector=True):
            payload = point.get("payload") or {}
            metadata = VectorMetadata(values=dict(payload.get("metadata") or {}))
            if matches(metadata.to_dict(), filters):
                matched.append(self._point_to_document(point))
        start = max(0, offset)
        if limit is not None:
            return matched[start : start + max(0, limit)]
        return matched[start:]

    async def _scroll_all(
        self,
        info: CollectionInfo,
        *,
        with_payload: bool,
        with_vector: bool = False,
    ) -> list[dict[str, Any]]:
        qn = _qname(info.namespace, info.name)
        points: list[dict[str, Any]] = []
        next_offset: Any = None
        while True:
            body: dict[str, Any] = {
                "limit": 100,
                "with_payload": with_payload,
                "with_vector": with_vector,
            }
            if next_offset is not None:
                body["offset"] = next_offset
            data = await self._http.request("POST", f"/collections/{qn}/points/scroll", json=body)
            result = data.get("result") or {}
            points.extend(result.get("points") or [])
            next_offset = result.get("next_page_offset")
            if next_offset is None:
                break
        return points

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
        await self._require_collection(ns, name)
        qn = _qname(ns, name)
        points = await self._retrieve_points(qn, [id], ns, name, with_vector=True)
        if not points:
            raise VectorStoreError(f"Document {id!r} not found in collection {name!r}")
        point = points[0]
        payload = point.get("payload") or {}
        payload["metadata"] = metadata.to_dict()
        await self._http.request(
            "PUT",
            f"/collections/{qn}/points",
            json={
                "points": [
                    {
                        "id": point["id"],
                        "vector": point["vector"],
                        "payload": payload,
                    }
                ]
            },
            params={"wait": "true"},
        )

    async def get_metadata(
        self,
        name: str,
        id: str,
        *,
        namespace: str | None = None,
    ) -> VectorMetadata:
        ns = namespace or self.default_namespace
        await self._require_collection(ns, name)
        qn = _qname(ns, name)
        points = await self._retrieve_points(qn, [id], ns, name)
        if not points:
            raise VectorStoreError(f"Document {id!r} not found in collection {name!r}")
        payload = points[0].get("payload") or {}
        return VectorMetadata(values=dict(payload.get("metadata") or {}))

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _point_to_document(self, point: dict[str, Any]) -> VectorDocument:
        payload = point.get("payload") or {}
        return VectorDocument(
            id=payload.get("_id", ""),
            vector=list(point.get("vector") or []),
            text=str(payload.get("text") or ""),
            metadata=VectorMetadata(values=dict(payload.get("metadata") or {})),
            version=int(payload.get("version") or 1),
        )


__all__ = ["QdrantVectorStore"]
