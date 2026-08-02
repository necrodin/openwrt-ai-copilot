"""Knowledge indexers — incremental document/chunk storage.

An indexer persists documents, chunks, collection info, and version history,
and decides what *happened* to each document during an ingest pass via its
checksum:

- **added** — id never seen before (version 1).
- **updated** — id known, checksum changed (version bumped).
- **unchanged** — id known, same checksum (version preserved; no re-write).
- **duplicate** — content (checksum) already indexed under a *different* id.
- **removed** — known id not present in a later pass (via :meth:`reconcile`).

Two implementations share this logic:

- :class:`InMemoryKnowledgeIndexer` — state in memory (default).
- :class:`FileSystemKnowledgeIndexer` — JSON state on disk, enabling true
  incremental indexing across process runs.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from knowledge.checksum import document_checksum
from knowledge.errors import KnowledgeIndexError
from knowledge.models import (
    KnowledgeChunk,
    KnowledgeCollection,
    KnowledgeDocument,
    KnowledgeVersion,
)
from knowledge.protocols import KnowledgeIndexer


def _now() -> datetime:
    return datetime.now(UTC)


class _BaseIndexer(KnowledgeIndexer):
    """Shared incremental indexing logic (checksum → version/duplicate)."""

    def _decide(
        self, collection_id: str, document: KnowledgeDocument, existing: KnowledgeDocument | None
    ) -> KnowledgeVersion:
        checksum = document.checksum or document_checksum(document.text)

        duplicate_of = self._checksum_owner(collection_id, checksum)
        if existing is None:
            if duplicate_of is not None and duplicate_of != document.id:
                return KnowledgeVersion(
                    document_id=document.id,
                    version=1,
                    checksum=checksum,
                    change="duplicate",
                    source=document.source,
                    indexed_at=_now(),
                )
            return KnowledgeVersion(
                document_id=document.id,
                version=max(1, document.version),
                checksum=checksum,
                change="added",
                source=document.source,
                indexed_at=_now(),
            )
        if existing.checksum == checksum:
            return KnowledgeVersion(
                document_id=document.id,
                version=existing.version,
                checksum=checksum,
                change="unchanged",
                source=document.source,
                indexed_at=_now(),
            )
        return KnowledgeVersion(
            document_id=document.id,
            version=existing.version + 1,
            checksum=checksum,
            change="updated",
            source=document.source,
            indexed_at=_now(),
        )

    def _checksum_owner(self, collection_id: str, checksum: str) -> str | None:
        for doc in self.documents(collection_id):
            if doc.checksum == checksum:
                return doc.id
        return None

    def ingest(
        self,
        document: KnowledgeDocument,
        chunks: list[KnowledgeChunk],
        *,
        collection_id: str,
    ) -> KnowledgeVersion:
        existing = self.get_document(document.id)
        version = self._decide(collection_id, document, existing)

        if version.change in ("unchanged", "duplicate"):
            return version

        checksum = version.checksum
        stored = document.model_copy(update={"checksum": checksum, "version": version.version})
        self._store(collection_id, stored, chunks)
        self._record_version(collection_id, version)
        return version

    # ------------------------------------------------------------------ #
    # Subclass hooks                                                      #
    # ------------------------------------------------------------------ #

    def _store(
        self, collection_id: str, document: KnowledgeDocument, chunks: list[KnowledgeChunk]
    ) -> None:
        raise NotImplementedError

    def _record_version(self, collection_id: str, version: KnowledgeVersion) -> None:
        raise NotImplementedError

    def reconcile(self, seen_ids: set[str], *, collection_id: str) -> list[KnowledgeVersion]:
        removed: list[KnowledgeVersion] = []
        for document in self.documents(collection_id):
            if document.id not in seen_ids:
                self._remove(document.id, collection_id)
                removed.append(
                    KnowledgeVersion(
                        document_id=document.id,
                        version=document.version,
                        checksum=document.checksum,
                        change="removed",
                        source=document.source,
                        indexed_at=_now(),
                    )
                )
        return removed

    def _remove(self, document_id: str, collection_id: str) -> None:
        raise NotImplementedError

    def find_duplicates(self, collection_id: str) -> dict[str, list[str]]:
        grouped: dict[str, list[str]] = {}
        for document in self.documents(collection_id):
            if not document.checksum:
                continue
            grouped.setdefault(document.checksum, []).append(document.id)
        return {checksum: ids for checksum, ids in grouped.items() if len(ids) > 1}


class InMemoryKnowledgeIndexer(_BaseIndexer):
    """In-memory indexer (no persistence across runs)."""

    indexer_type = "memory"

    def __init__(self) -> None:
        self._collections: dict[str, KnowledgeCollection] = {}
        self._documents: dict[str, dict[str, KnowledgeDocument]] = {}
        self._chunks: dict[str, dict[str, list[KnowledgeChunk]]] = {}
        self._versions: dict[str, list[KnowledgeVersion]] = {}

    def exists(self, document_id: str) -> bool:
        return any(document_id in docs for docs in self._documents.values())

    def _store(
        self, collection_id: str, document: KnowledgeDocument, chunks: list[KnowledgeChunk]
    ) -> None:
        if collection_id not in self._collections:
            self._collections[collection_id] = KnowledgeCollection(
                id=collection_id, name=collection_id, created_at=_now()
            )
        self._documents.setdefault(collection_id, {})[document.id] = document
        self._chunks.setdefault(collection_id, {})[document.id] = chunks

        collection = self._collections[collection_id]
        if document.id not in collection.document_ids:
            collection.document_ids.append(document.id)
        collection.chunk_count = sum(
            len(doc_chunks) for doc_chunks in self._chunks[collection_id].values()
        )
        collection.updated_at = _now()

    def _record_version(self, collection_id: str, version: KnowledgeVersion) -> None:
        self._versions.setdefault(collection_id, []).append(version)

    def _remove(self, document_id: str, collection_id: str) -> None:
        self._documents.get(collection_id, {}).pop(document_id, None)
        self._chunks.get(collection_id, {}).pop(document_id, None)
        collection = self._collections.get(collection_id)
        if collection is not None and document_id in collection.document_ids:
            collection.document_ids.remove(document_id)

    def documents(self, collection_id: str) -> list[KnowledgeDocument]:
        return list(self._documents.get(collection_id, {}).values())

    def chunks(self, document_id: str) -> list[KnowledgeChunk]:
        for chunks in self._chunks.values():
            if document_id in chunks:
                return chunks[document_id]
        return []

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        for docs in self._documents.values():
            if document_id in docs:
                return docs[document_id]
        return None

    def collection(self, collection_id: str) -> KnowledgeCollection | None:
        return self._collections.get(collection_id)

    def collections(self) -> list[KnowledgeCollection]:
        return list(self._collections.values())

    def versions(self, collection_id: str) -> list[KnowledgeVersion]:
        return list(self._versions.get(collection_id, []))

    def flush(self) -> None:
        return None


class FileSystemKnowledgeIndexer(_BaseIndexer):
    """JSON-persisted indexer enabling incremental indexing across runs.

    State lives under ``root`` as one JSON file per collection. An empty
    ``root`` disables persistence (behaves like the in-memory indexer).
    """

    indexer_type = "filesystem"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root) if root else None
        self._state: dict[str, Any] = {}
        if self._root is not None:
            self._root.mkdir(parents=True, exist_ok=True)
            self._load_state()

    def _state_path(self, collection_id: str) -> Path:
        assert self._root is not None
        return self._root / f"{collection_id}.json"

    def _load_state(self) -> None:
        assert self._root is not None
        for path in self._root.glob("*.json"):
            collection_id = path.stem
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError) as exc:
                raise KnowledgeIndexError(f"Could not load index state {path}: {exc}") from exc
            self._state[collection_id] = data

    def _ensure(self, collection_id: str) -> dict[str, Any]:
        if collection_id not in self._state:
            self._state[collection_id] = {
                "collection": KnowledgeCollection(
                    id=collection_id, name=collection_id, created_at=_now()
                ).model_dump(mode="json"),
                "documents": {},
                "chunks": {},
                "versions": [],
            }
        return self._state[collection_id]

    def exists(self, document_id: str) -> bool:
        return any(document_id in entry["documents"] for entry in self._state.values())

    def _store(
        self, collection_id: str, document: KnowledgeDocument, chunks: list[KnowledgeChunk]
    ) -> None:
        entry = self._ensure(collection_id)
        entry["documents"][document.id] = document.model_dump(mode="json")
        entry["chunks"][document.id] = [chunk.model_dump(mode="json") for chunk in chunks]
        if document.id not in entry["collection"]["document_ids"]:
            entry["collection"]["document_ids"].append(document.id)
        entry["collection"]["chunk_count"] = sum(
            len(doc_chunks) for doc_chunks in entry["chunks"].values()
        )
        entry["collection"]["updated_at"] = _now().isoformat()
        self.flush()

    def _record_version(self, collection_id: str, version: KnowledgeVersion) -> None:
        entry = self._ensure(collection_id)
        entry["versions"].append(version.model_dump(mode="json"))
        self.flush()

    def _remove(self, document_id: str, collection_id: str) -> None:
        entry = self._state.get(collection_id)
        if entry is None:
            return
        entry["documents"].pop(document_id, None)
        entry["chunks"].pop(document_id, None)
        ids = entry["collection"].get("document_ids", [])
        if document_id in ids:
            ids.remove(document_id)
        self.flush()

    def documents(self, collection_id: str) -> list[KnowledgeDocument]:
        entry = self._state.get(collection_id)
        if entry is None:
            return []
        return [KnowledgeDocument.model_validate(data) for data in entry["documents"].values()]

    def chunks(self, document_id: str) -> list[KnowledgeChunk]:
        for entry in self._state.values():
            if document_id in entry["chunks"]:
                data = entry["chunks"][document_id]
                return [KnowledgeChunk.model_validate(item) for item in data]
        return []

    def get_document(self, document_id: str) -> KnowledgeDocument | None:
        for entry in self._state.values():
            if document_id in entry["documents"]:
                return KnowledgeDocument.model_validate(entry["documents"][document_id])
        return None

    def collection(self, collection_id: str) -> KnowledgeCollection | None:
        entry = self._state.get(collection_id)
        if entry is None:
            return None
        return KnowledgeCollection.model_validate(entry["collection"])

    def collections(self) -> list[KnowledgeCollection]:
        return [
            KnowledgeCollection.model_validate(entry["collection"])
            for entry in self._state.values()
        ]

    def versions(self, collection_id: str) -> list[KnowledgeVersion]:
        entry = self._state.get(collection_id)
        if entry is None:
            return []
        return [KnowledgeVersion.model_validate(data) for data in entry["versions"]]

    def flush(self) -> None:
        if self._root is None:
            return
        for collection_id, entry in self._state.items():
            try:
                self._state_path(collection_id).write_text(
                    json.dumps(entry, indent=2), encoding="utf-8"
                )
            except OSError as exc:
                raise KnowledgeIndexError(f"Could not flush index state: {exc}") from exc


__all__ = ["FileSystemKnowledgeIndexer", "InMemoryKnowledgeIndexer"]
