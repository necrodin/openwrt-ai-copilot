"""Chroma vector store — thin HTTP REST adapter (no SDK).

Talks to the Chroma server REST API (``/api/v1/tenants/{tenant}/databases/{db}
/collections``, ``/api/v1/collections/{id}/{add,upsert,query,get,delete}``)
through :class:`VectorStoreHttpClient`. Namespaces are encoded into the Chroma
collection name (``<namespace>__<name>``, sanitized). Collections are created
with the ``hnsw:space=cosine`` so returned distances are ``1 - similarity``.

Full metadata (arbitrary JSON) travels inside the Chroma metadata record under
the reserved ``_meta`` key (a JSON string), with ``_version`` as an integer —
this keeps any user metadata keys usable. Filters use the shared pure-Python
matcher so every backend has identical semantics.
"""

from __future__ import annotations

import json
import re
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


def _collection_metadata(namespace: str, name: str, dimension: int) -> dict[str, Any]:
    return {
        "hnsw:space": "cosine",
        _MARKER: True,
        "namespace": namespace,
        "name": name,
        "dimension": dimension,
    }


class ChromaVectorStore(VectorStore):
    """Chroma-backed :class:`VectorStore` over its server REST API."""

    provider_type = "chroma"

    def __init__(self, config: Any, *, client: Any | None = None) -> None:
        self.name = config.effective_name()
        self.default_namespace = config.default_namespace or DEFAULT_NAMESPACE
        self._tenant = config.tenant
        self._database = config.database
        self._http = VectorStoreHttpClient(
            base_url=config.effective_base_url(),
            api_key=None,
            headers=config.extra_headers,
            timeout_seconds=config.timeout_seconds,
            verify_tls=config.verify_tls,
            client=client,
        )

    # ------------------------------------------------------------------ #
    # Plumbing                                                           #
    # ------------------------------------------------------------------ #

    async def health(self) -> bool:
        try:
            await self._http.request("GET", self._collections_path())
            return True
        except Exception:  # noqa: BLE001 - health must never raise
            return False

    async def aclose(self) -> None:
        await self._http.aclose()

    def _collections_path(self) -> str:
        return f"/api/v1/tenants/{self._tenant}/databases/{self._database}/collections"

    async def _get_collection(self, name: str, ns: str) -> dict[str, Any] | None:
        try:
            data = await self._http.request(
                "GET",
                self._collections_path(),
                params={"name": _qname(ns, name)},
            )
        except VectorStoreHttpStatusError as exc:
            if exc.status_code == 404:
                return None
            raise
        if isinstance(data, list):
            return data[0] if data else None
        return data

    async def _require_collection(self, name: str, ns: str) -> dict[str, Any]:
        collection = await self._get_collection(name, ns)
        if collection is None:
            raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
        return collection

    def _marker_dimension(self, collection: dict[str, Any]) -> int:
        metadata = collection.get("metadata") or {}
        return int(metadata.get("dimension") or 0)

    def _encode_metadata(self, metadata: VectorMetadata, version: int) -> dict[str, Any]:
        return {
            "_meta": json.dumps(metadata.to_dict(), separators=(",", ":")),
            "_version": version,
        }

    def _decode_metadata(self, record: dict[str, Any]) -> tuple[VectorMetadata, int]:
        version = int(record.get("_version") or 1)
        raw = record.get("_meta") or "{}"
        try:
            values = json.loads(raw)
        except ValueError:
            values = {}
        return VectorMetadata(values=values), version

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
        marker = _collection_metadata(ns, name, dimension)
        marker.update((metadata or VectorMetadata()).to_dict())
        try:
            await self._http.request(
                "POST",
                self._collections_path(),
                json={"name": _qname(ns, name), "metadata": marker},
            )
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
        collection = await self._require_collection(name, ns)
        await self._http.request("DELETE", f"/api/v1/collections/{collection['id']}")

    async def list_collections(
        self,
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[CollectionInfo]:
        data = await self._http.request("GET", self._collections_path())
        infos: list[CollectionInfo] = []
        for item in data or []:
            name = item.get("name") or ""
            if "__" not in name:
                continue
            ns, short = name.rsplit("__", 1)
            metadata = item.get("metadata") or {}
            if not metadata.get(_MARKER):
                continue
            if namespace is not None and ns != namespace:
                continue
            dimension = int(metadata.get("dimension") or 0)
            count = await self._count(item["id"])
            infos.append(
                CollectionInfo(
                    name=short,
                    namespace=ns,
                    dimension=dimension,
                    distance=DISTANCE_COSINE,
                    metadata=VectorMetadata(
                        values={
                            key: value
                            for key, value in metadata.items()
                            if key not in (_MARKER, "namespace", "name", "dimension", "hnsw:space")
                        }
                    ),
                    version=1,
                    document_count=count,
                    created_at=datetime.now(UTC),
                )
            )
        infos.sort(key=lambda entry: (entry.namespace, entry.name))
        start = max(0, offset)
        if limit is not None:
            return infos[start : start + max(0, limit)]
        return infos[start:]

    async def _count(self, collection_id: str) -> int:
        data = await self._http.request("GET", f"/api/v1/collections/{collection_id}/count")
        return int(data or 0)

    async def collection_info(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionInfo | None:
        ns = namespace or self.default_namespace
        collection = await self._get_collection(name, ns)
        if collection is None:
            return None
        metadata = collection.get("metadata") or {}
        if not metadata.get(_MARKER):
            return None
        user_metadata = VectorMetadata(
            values={
                key: value
                for key, value in metadata.items()
                if key not in (_MARKER, "namespace", "name", "dimension", "hnsw:space")
            }
        )
        return CollectionInfo(
            name=name,
            namespace=ns,
            dimension=self._marker_dimension(collection),
            distance=DISTANCE_COSINE,
            metadata=user_metadata,
            version=1,
            document_count=await self._count(collection["id"]),
            created_at=datetime.now(UTC),
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
        max_version = 0
        for document in await self._get_all(info):
            max_version = max(max_version, document.version)
        return CollectionStats(
            name=name,
            namespace=ns,
            document_count=info.document_count,
            dimension=info.dimension,
            max_version=max_version,
            created_at=info.created_at,
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
        collection = await self._require_collection(name, ns)
        dimension = self._marker_dimension(collection)
        self._validate_dimension(name, dimension, documents)
        if not documents:
            return []
        existing = await self._get_records(
            collection["id"], [doc.id for doc in documents], include_embeddings=False
        )
        if existing["ids"]:
            raise VectorStoreError(
                f"One or more document ids already exist in collection {name!r}; "
                "use update_documents to replace"
            )
        await self._http.request(
            "POST",
            f"/api/v1/collections/{collection['id']}/add",
            json={
                "ids": [doc.id for doc in documents],
                "embeddings": [doc.vector for doc in documents],
                "documents": [doc.text for doc in documents],
                "metadatas": [
                    self._encode_metadata(doc.metadata, max(1, doc.version)) for doc in documents
                ],
            },
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
        collection = await self._require_collection(name, ns)
        dimension = self._marker_dimension(collection)
        self._validate_dimension(name, dimension, documents)
        if not documents:
            return 0
        existing = await self._get_records(
            collection["id"], [doc.id for doc in documents], include_embeddings=False
        )
        versions: dict[str, int] = {}
        for record_id, record in zip(existing["ids"], existing["metadatas"], strict=True):
            _, version = self._decode_metadata(record or {})
            versions[record_id] = version
        ids: list[str] = []
        embeddings: list[list[float]] = []
        texts: list[str] = []
        metadatas: list[dict[str, Any]] = []
        for doc in documents:
            version = versions.get(doc.id, 0) + 1 if doc.id in versions else max(1, doc.version)
            ids.append(doc.id)
            embeddings.append(doc.vector)
            texts.append(doc.text)
            metadatas.append(self._encode_metadata(doc.metadata, version))
        await self._http.request(
            "POST",
            f"/api/v1/collections/{collection['id']}/upsert",
            json={
                "ids": ids,
                "embeddings": embeddings,
                "documents": texts,
                "metadatas": metadatas,
            },
        )
        return len(ids)

    async def delete_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> int:
        ns = namespace or self.default_namespace
        collection = await self._require_collection(name, ns)
        if not ids:
            return 0
        existing = await self._get_records(collection["id"], ids, include_embeddings=False)
        if not existing["ids"]:
            return 0
        await self._http.request(
            "POST",
            f"/api/v1/collections/{collection['id']}/delete",
            json={"ids": existing["ids"]},
        )
        return len(existing["ids"])

    async def get_documents(
        self,
        name: str,
        ids: list[str],
        *,
        namespace: str | None = None,
    ) -> list[VectorDocument]:
        ns = namespace or self.default_namespace
        collection = await self._require_collection(name, ns)
        if not ids:
            return []
        records = await self._get_records(collection["id"], ids, include_embeddings=True)
        by_id = dict(
            zip(
                records["ids"],
                self._records_to_documents(records),
                strict=True,
            )
        )
        return [by_id[doc_id] for doc_id in ids if doc_id in by_id]

    async def _get_records(
        self,
        collection_id: str,
        ids: list[str],
        *,
        include_embeddings: bool,
    ) -> dict[str, Any]:
        include = ["documents", "metadatas"]
        if include_embeddings:
            include.append("embeddings")
        data = await self._http.request(
            "POST",
            f"/api/v1/collections/{collection_id}/get",
            json={"ids": ids, "include": include},
        )
        return data or {}

    def _records_to_documents(self, records: dict[str, Any]) -> list[VectorDocument]:
        ids = records.get("ids") or []
        documents = records.get("documents") or []
        metadatas = records.get("metadatas") or []
        embeddings = records.get("embeddings") or []
        result: list[VectorDocument] = []
        for index, record_id in enumerate(ids):
            metadata, version = self._decode_metadata(metadatas[index] or {})
            result.append(
                VectorDocument(
                    id=record_id,
                    vector=list(embeddings[index] or []) if embeddings else [],
                    text=str(documents[index] or "") if documents else "",
                    metadata=metadata,
                    version=version,
                )
            )
        return result

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
        collection = await self._require_collection(name, ns)
        dimension = self._marker_dimension(collection)
        if len(request.query_vector) != dimension:
            raise DimensionMismatchError(
                f"Query has {len(request.query_vector)} dimensions; "
                f"collection {name!r} expects {dimension}"
            )
        include = ["documents", "metadatas", "distances"]
        if request.include_vectors:
            include.append("embeddings")
        pool_size = max(1, request.top_k, request.offset + (request.limit or 0))
        data = await self._http.request(
            "POST",
            f"/api/v1/collections/{collection['id']}/query",
            json={
                "query_embeddings": [request.query_vector],
                "n_results": pool_size,
                "include": include,
            },
        )
        ids = (data.get("ids") or [[]])[0]
        distances = (data.get("distances") or [[]])[0]
        documents = (data.get("documents") or [[]])[0]
        metadatas = (data.get("metadatas") or [[]])[0]
        embeddings = (data.get("embeddings") or [[]])[0]

        results: list[SearchResult] = []
        for index, record_id in enumerate(ids):
            metadata, version = self._decode_metadata(metadatas[index] or {})
            if not matches(metadata.to_dict(), request.filters):
                continue
            score = 1.0 - float(distances[index] or 0.0)
            results.append(
                SearchResult(
                    id=record_id,
                    score=max(-1.0, min(1.0, score)),
                    text=str(documents[index] or "") if documents else "",
                    metadata=metadata,
                    vector=list(embeddings[index] or []) if embeddings else [],
                    version=version,
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
        info = await self.collection_info(name, namespace=ns)
        if info is None:
            raise CollectionNotFoundError(f"Collection {name!r} not found in namespace {ns!r}")
        collection = await self._require_collection(name, ns)
        matched: list[VectorDocument] = []
        for document in await self._get_all(info, collection_id=collection["id"]):
            if matches(document.metadata.to_dict(), filters):
                matched.append(document)
        start = max(0, offset)
        if limit is not None:
            return matched[start : start + max(0, limit)]
        return matched[start:]

    async def _get_all(
        self,
        info: CollectionInfo,
        *,
        collection_id: str | None = None,
    ) -> list[VectorDocument]:
        cid = collection_id
        if cid is None:
            collection = await self._require_collection(info.name, info.namespace)
            cid = collection["id"]
        documents: list[VectorDocument] = []
        offset = 0
        page_size = 100
        while True:
            data = (
                await self._http.request(
                    "POST",
                    f"/api/v1/collections/{cid}/get",
                    json={
                        "include": ["documents", "metadatas", "embeddings"],
                        "limit": page_size,
                        "offset": offset,
                    },
                )
                or {}
            )
            records = data.get("ids") or []
            documents.extend(self._records_to_documents(data))
            if len(records) < page_size:
                break
            offset += len(records)
        return documents

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
        collection = await self._require_collection(name, ns)
        existing = await self._get_records(collection["id"], [id], include_embeddings=True)
        if not existing["ids"]:
            raise VectorStoreError(f"Document {id!r} not found in collection {name!r}")
        record = self._records_to_documents(existing)[0]
        await self._http.request(
            "POST",
            f"/api/v1/collections/{collection['id']}/update",
            json={
                "ids": [id],
                "embeddings": [record.vector],
                "documents": [record.text],
                "metadatas": [self._encode_metadata(metadata, record.version)],
            },
        )

    async def get_metadata(
        self,
        name: str,
        id: str,
        *,
        namespace: str | None = None,
    ) -> VectorMetadata:
        ns = namespace or self.default_namespace
        collection = await self._require_collection(name, ns)
        existing = await self._get_records(collection["id"], [id], include_embeddings=False)
        if not existing["ids"]:
            raise VectorStoreError(f"Document {id!r} not found in collection {name!r}")
        record = self._records_to_documents(existing)[0]
        return record.metadata

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _validate_dimension(
        self, name: str, dimension: int, documents: list[VectorDocument]
    ) -> None:
        for doc in documents:
            if len(doc.vector) != dimension:
                raise DimensionMismatchError(
                    f"Document {doc.id!r} has {len(doc.vector)} dimensions; "
                    f"collection {name!r} expects {dimension}"
                )


__all__ = ["ChromaVectorStore"]
