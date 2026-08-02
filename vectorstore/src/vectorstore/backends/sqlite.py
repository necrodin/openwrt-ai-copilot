"""SQLite vector store — the offline reference implementation.

Uses the Python standard library ``sqlite3`` and a pure-Python cosine similarity
implementation, so it is always available (matching the project's offline /
air-gapped constraint) and serves as the behavioral reference every other
backend matches.

Vectors are stored as JSON text; every database call runs inside
``asyncio.to_thread`` so the event loop is never blocked.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from vectorstore.backends._filters import matches, validate_filters
from vectorstore.backends._math import cosine_similarity
from vectorstore.errors import (
    CollectionExistsError,
    CollectionNotFoundError,
    DimensionMismatchError,
    DocumentNotFoundError,
    VectorStoreConnectionError,
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

_SCHEMA = """
CREATE TABLE IF NOT EXISTS collections (
    namespace    TEXT NOT NULL,
    name         TEXT NOT NULL,
    dimension    INTEGER NOT NULL,
    distance     TEXT NOT NULL DEFAULT 'cosine',
    metadata     TEXT NOT NULL DEFAULT '{}',
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (namespace, name)
);
CREATE TABLE IF NOT EXISTS documents (
    namespace    TEXT NOT NULL,
    collection   TEXT NOT NULL,
    id           TEXT NOT NULL,
    vector       TEXT NOT NULL,
    text         TEXT NOT NULL DEFAULT '',
    metadata     TEXT NOT NULL DEFAULT '{}',
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL,
    PRIMARY KEY (namespace, collection, id)
);
"""


def _utcnow() -> str:
    return datetime.now(UTC).isoformat()


def _decode_vector(raw: str) -> list[float]:
    return json.loads(raw)


def _encode_metadata(metadata: VectorMetadata | None) -> str:
    return json.dumps((metadata or VectorMetadata()).to_dict())


def _decode_metadata(raw: str) -> VectorMetadata:
    return VectorMetadata(values=json.loads(raw))


class SQLiteVectorStore(VectorStore):
    """SQLite-backed :class:`VectorStore` (reference implementation)."""

    provider_type = "sqlite"

    def __init__(self, config: Any, **_: Any) -> None:
        self.name = config.effective_name()
        self.default_namespace = config.default_namespace or DEFAULT_NAMESPACE
        self._path = Path(config.effective_path())
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    # ------------------------------------------------------------------ #
    # Connections                                                        #
    # ------------------------------------------------------------------ #

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=10.0)
        connection.row_factory = sqlite3.Row
        return connection

    def _init_schema(self) -> None:
        with self._connect() as connection:
            connection.executescript(_SCHEMA)

    async def _run(self, operation: Any) -> Any:
        try:
            return await asyncio.to_thread(operation)
        except sqlite3.OperationalError as exc:
            raise VectorStoreConnectionError(f"SQLite error: {exc}") from exc

    async def health(self) -> bool:
        def check() -> bool:
            try:
                with self._connect() as connection:
                    connection.execute("SELECT 1")
                return True
            except sqlite3.Error:
                return False

        return bool(await asyncio.to_thread(check))

    async def aclose(self) -> None:
        return None

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
        now = _utcnow()

        def create() -> CollectionInfo:
            with self._connect() as connection:
                try:
                    connection.execute(
                        "INSERT INTO collections "
                        "(namespace, name, dimension, distance, metadata, version, created_at) "
                        "VALUES (?, ?, ?, ?, ?, 1, ?)",
                        (ns, name, dimension, DISTANCE_COSINE, _encode_metadata(metadata), now),
                    )
                except sqlite3.IntegrityError as exc:
                    raise CollectionExistsError(
                        f"Collection {name!r} already exists in namespace {ns!r}"
                    ) from exc
            return CollectionInfo(
                name=name,
                namespace=ns,
                dimension=dimension,
                distance=DISTANCE_COSINE,
                metadata=(metadata or VectorMetadata()),
                version=1,
                document_count=0,
                created_at=datetime.fromisoformat(now),
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
            with self._connect() as connection:
                cursor = connection.execute(
                    "DELETE FROM collections WHERE namespace = ? AND name = ?", (ns, name)
                )
                connection.execute(
                    "DELETE FROM documents WHERE namespace = ? AND collection = ?",
                    (ns, name),
                )
                if cursor.rowcount == 0:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )

        await self._run(delete)

    async def list_collections(
        self,
        *,
        namespace: str | None = None,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[CollectionInfo]:
        def list_all() -> list[CollectionInfo]:
            params: list[Any] = []
            where = ""
            if namespace is not None:
                where = "WHERE namespace = ?"
                params.append(namespace)
            limit_sql = ""
            if limit is not None:
                limit_sql = "LIMIT ? OFFSET ?"
                params.extend([max(0, limit), max(0, offset)])
            elif offset:
                limit_sql = "LIMIT -1 OFFSET ?"
                params.append(max(0, offset))
            with self._connect() as connection:
                rows = connection.execute(
                    f"SELECT * FROM collections {where} ORDER BY namespace, name {limit_sql}",
                    params,
                ).fetchall()
            return [self._row_to_info(row) for row in rows]

        return await self._run(list_all)

    async def collection_info(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionInfo | None:
        ns = namespace or self.default_namespace

        def info() -> CollectionInfo | None:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
            if row is None:
                return None
            return self._row_to_info(row)

        return await self._run(info)

    async def stats(
        self,
        name: str,
        *,
        namespace: str | None = None,
    ) -> CollectionStats:
        ns = namespace or self.default_namespace

        def compute() -> CollectionStats:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT * FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                doc_row = connection.execute(
                    "SELECT COUNT(*) AS count, "
                    "COALESCE(MAX(updated_at), MAX(created_at)) AS updated_at, "
                    "MAX(version) AS max_version "
                    "FROM documents WHERE namespace = ? AND collection = ?",
                    (ns, name),
                ).fetchone()
            return CollectionStats(
                name=name,
                namespace=ns,
                document_count=int(doc_row["count"]),
                dimension=int(row["dimension"]),
                max_version=int(doc_row["max_version"] or 0),
                created_at=datetime.fromisoformat(row["created_at"]),
                updated_at=(
                    datetime.fromisoformat(doc_row["updated_at"]) if doc_row["updated_at"] else None
                ),
            )

        return await self._run(compute)

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
        now = _utcnow()

        def add() -> list[str]:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT dimension FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                dimension = int(row["dimension"])
                for doc in documents:
                    if len(doc.vector) != dimension:
                        raise DimensionMismatchError(
                            f"Document {doc.id!r} has {len(doc.vector)} dimensions; "
                            f"collection {name!r} expects {dimension}"
                        )
                try:
                    connection.executemany(
                        "INSERT INTO documents "
                        "(namespace, collection, id, vector, text, metadata, "
                        "version, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        [
                            (
                                ns,
                                name,
                                doc.id,
                                json.dumps(doc.vector),
                                doc.text,
                                _encode_metadata(doc.metadata),
                                max(1, doc.version),
                                now,
                                now,
                            )
                            for doc in documents
                        ],
                    )
                except sqlite3.IntegrityError as exc:
                    raise VectorStoreError(
                        f"One or more document ids already exist in collection {name!r}; "
                        "use update_documents to replace"
                    ) from exc
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
        now = _utcnow()

        def update() -> int:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT dimension FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                dimension = int(row["dimension"])
                for doc in documents:
                    if len(doc.vector) != dimension:
                        raise DimensionMismatchError(
                            f"Document {doc.id!r} has {len(doc.vector)} dimensions; "
                            f"collection {name!r} expects {dimension}"
                        )
                changed = 0
                for doc in documents:
                    existing = connection.execute(
                        "SELECT version FROM documents "
                        "WHERE namespace = ? AND collection = ? AND id = ?",
                        (ns, name, doc.id),
                    ).fetchone()
                    version = (int(existing["version"]) + 1) if existing else max(1, doc.version)
                    connection.execute(
                        "INSERT INTO documents "
                        "(namespace, collection, id, vector, text, metadata, "
                        "version, created_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                        "ON CONFLICT(namespace, collection, id) DO UPDATE SET "
                        "vector = excluded.vector, text = excluded.text, "
                        "metadata = excluded.metadata, version = excluded.version, "
                        "updated_at = excluded.updated_at",
                        (
                            ns,
                            name,
                            doc.id,
                            json.dumps(doc.vector),
                            doc.text,
                            _encode_metadata(doc.metadata),
                            version,
                            now,
                            now,
                        ),
                    )
                    changed += 1
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
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                if not ids:
                    return 0
                placeholders = ",".join("?" * len(ids))
                cursor = connection.execute(
                    "DELETE FROM documents "
                    f"WHERE namespace = ? AND collection = ? AND id IN ({placeholders})",
                    (ns, name, *ids),
                )
                return cursor.rowcount

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
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                if not ids:
                    return []
                rows = connection.execute(
                    "SELECT * FROM documents "
                    "WHERE namespace = ? AND collection = ? AND id IN ({})".format(
                        ",".join("?" * len(ids))
                    ),
                    (ns, name, *ids),
                ).fetchall()
            by_id = {row["id"]: self._row_to_document(row) for row in rows}
            return [by_id[doc_id] for doc_id in ids if doc_id in by_id]

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
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT dimension FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                dimension = int(row["dimension"])
                if len(request.query_vector) != dimension:
                    raise DimensionMismatchError(
                        f"Query has {len(request.query_vector)} dimensions; "
                        f"collection {name!r} expects {dimension}"
                    )
                rows = connection.execute(
                    "SELECT * FROM documents WHERE namespace = ? AND collection = ?",
                    (ns, name),
                ).fetchall()
            results: list[SearchResult] = []
            for doc_row in rows:
                document = self._row_to_document(doc_row)
                metadata = document.metadata.to_dict()
                if not matches(metadata, request.filters):
                    continue
                score = cosine_similarity(request.query_vector, document.vector)
                results.append(
                    SearchResult(
                        id=document.id,
                        score=score,
                        text=document.text,
                        metadata=document.metadata,
                        vector=document.vector if request.include_vectors else [],
                        version=document.version,
                    )
                )
            results.sort(key=lambda item: item.score, reverse=True)
            candidates = results[: request.top_k] if request.top_k else results
            start = max(0, request.offset)
            if request.limit is not None:
                return candidates[start : start + max(0, request.limit)]
            return candidates[start:]

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
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT 1 FROM collections WHERE namespace = ? AND name = ?",
                    (ns, name),
                ).fetchone()
                if row is None:
                    raise CollectionNotFoundError(
                        f"Collection {name!r} not found in namespace {ns!r}"
                    )
                rows = connection.execute(
                    "SELECT * FROM documents WHERE namespace = ? AND collection = ?",
                    (ns, name),
                ).fetchall()
            matched = [
                self._row_to_document(doc_row)
                for doc_row in rows
                if matches(self._row_to_document(doc_row).metadata.to_dict(), filters)
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
        now = _utcnow()

        def set_meta() -> None:
            with self._connect() as connection:
                cursor = connection.execute(
                    "UPDATE documents SET metadata = ?, updated_at = ? "
                    "WHERE namespace = ? AND collection = ? AND id = ?",
                    (_encode_metadata(metadata), now, ns, name, id),
                )
                if cursor.rowcount == 0:
                    raise DocumentNotFoundError(f"Document {id!r} not found in collection {name!r}")

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
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT metadata FROM documents "
                    "WHERE namespace = ? AND collection = ? AND id = ?",
                    (ns, name, id),
                ).fetchone()
            if row is None:
                raise DocumentNotFoundError(f"Document {id!r} not found in collection {name!r}")
            return _decode_metadata(row["metadata"])

        return await self._run(get_meta)

    # ------------------------------------------------------------------ #
    # Helpers                                                            #
    # ------------------------------------------------------------------ #

    def _row_to_info(self, row: sqlite3.Row) -> CollectionInfo:
        with self._connect() as connection:
            count = connection.execute(
                "SELECT COUNT(*) AS count FROM documents WHERE namespace = ? AND collection = ?",
                (row["namespace"], row["name"]),
            ).fetchone()["count"]
        return CollectionInfo(
            name=row["name"],
            namespace=row["namespace"],
            dimension=int(row["dimension"]),
            distance=row["distance"],
            metadata=_decode_metadata(row["metadata"]),
            version=int(row["version"]),
            document_count=int(count),
            created_at=datetime.fromisoformat(row["created_at"]),
        )

    def _row_to_document(self, row: sqlite3.Row) -> VectorDocument:
        return VectorDocument(
            id=row["id"],
            vector=_decode_vector(row["vector"]),
            text=row["text"],
            metadata=_decode_metadata(row["metadata"]),
            version=int(row["version"]),
        )


__all__ = ["SQLiteVectorStore"]
