# Sprint 7 — Provider-Independent Vector Database Layer

Status: **complete** (verification: 233 pytest passed, ruff clean; no network —
all provider calls go through mocked transports).

## Goal

A provider-independent vector database layer: store, search, and manage vector
documents through **any** configured backend — SQLite (offline reference),
Chroma, Qdrant, FAISS — behind one async `VectorStore` interface. No vendor SDK
is imported anywhere: Chroma and Qdrant are driven through their documented
HTTP REST APIs, FAISS is an optional in-process backend, SQLite is the
dependency-free reference. No RAG, no retrieval pipeline, no chat changes —
this sprint only builds the storage capability.

## Design decisions

### One interface, four backends

`VectorStore` (`vectorstore/src/vectorstore/protocols.py`) is the single
contract. Everything downstream (managers, future RAG) depends only on this
abstraction:

- **Collections**: `create_collection`, `delete_collection`, `list_collections`,
  `collection_info`, `stats`.
- **Documents**: `add_documents` (batch insert), `update_documents` (upsert,
  versioned), `delete_documents`, `get_documents`.
- **Search**: `search` (similarity + filters + pagination), `filter_documents`
  (metadata-only query).
- **Metadata**: `set_metadata`, `get_metadata`.
- **Plumbing**: `health`, `aclose`, `name`, `default_namespace`.

Every backend implements the exact same semantics:

| Feature | Behaviour |
|---|---|
| Score | cosine similarity (higher is better); distance fixed to `cosine`. |
| Namespaces | `namespace=None` falls back to the store's `default_namespace` (default `"default"`); HTTP/FAISS backends encode namespaces into collection names (`<namespace>__<name>`, sanitized) since they lack native namespaces. |
| Filters | AND-combined leaf clauses (`eq, ne, gt, gte, lt, lte, in, not_in, contains`) evaluated by a shared pure-Python matcher (`backends/_filters.py`) so every backend has identical semantics. |
| Pagination | `offset` / `limit` on list, search, and filter operations (`limit=None` = no limit). |
| Versioning | `VectorDocument.version` starts at 1 and auto-increments on every `update_documents` replacement. |

### Backends

- **SQLite** (`backends/sqlite.py`) — the reference implementation. Standard
  library only (`sqlite3`, pure-Python `cosine_similarity`); all database calls
  run inside `asyncio.to_thread` so the event loop is never blocked. Vectors
  and metadata are stored as JSON text.
- **Chroma** (`backends/chroma.py`) — HTTP REST adapter (`/api/v1/tenants/
  {tenant}/databases/{db}/collections`, `/api/v1/collections/{id}/...`). Full
  arbitrary metadata travels inside the Chroma metadata record under the
  reserved `_meta` (JSON string) and `_version` (int) keys. Query distances are
  converted back to cosine scores (`score = 1 - distance`).
- **Qdrant** (`backends/qdrant.py`) — HTTP REST adapter
  (`/collections`, `/collections/{name}/points`, `.../search`, `.../scroll`,
  `.../delete`). Arbitrary document ids are mapped to stable UUIDs on the wire
  (the original id travels in the point payload). Collection metadata carries a
  marker so foreign Qdrant collections are ignored.
- **FAISS** (`backends/faiss.py`) — optional in-process backend (lazy
  `faiss-cpu` + `numpy` import; clear `VectorStoreError` if missing). One
  `IndexFlatIP` over L2-normalized vectors per collection (inner product =
  cosine) plus a JSON sidecar. Updates/deletes rebuild the index (FAISS has no
  native remove). The `[faiss]` extra installs it.

Shared plumbing: `backends/_math.py` (pure-Python cosine), `backends/_filters.py`
(matcher + validation), `backends/_http.py` (`VectorStoreHttpClient` with error
normalization — network failures → `VectorStoreConnectionError`, 401/403 →
`VectorStoreAuthError`, other non-2xx → `VectorStoreHttpStatusError` carrying
the status so backends translate 404/409). The HTTP client accepts an injected
`httpx.AsyncClient` so tests run against `MockTransport` with no network.

### Configuration & factory

Stores are selected entirely through configuration, never code
(`vectorstore/src/vectorstore/config.py`):

- `VectorStoreConfig` — per-store settings (`type`, `path`/`base_url`,
  `api_key_env`/`api_key_ref` for secrets referenced by environment variable
  name, `extra_headers`, `timeout_seconds`, `verify_tls`, `default_namespace`,
  Chroma `tenant`/`database`). Defaults: SQLite path `data/vectorstore.sqlite3`,
  FAISS dir `data/vectorstore_faiss`, Qdrant `http://localhost:6333`,
  Chroma `http://localhost:8000`.
- `VectorStoresConfig` — `default_store` + `stores`; loads from YAML/TOML
  (`from_file`) or dict (`from_dict`); each store's `type` defaults to its
  config key.

`VectorStoreFactory` (`vectorstore/src/vectorstore/factory.py`) turns the
config into lazily-created, cached `VectorStore` instances:

| Method | Behaviour |
|---|---|
| `get(name=None)` | Return a store by name, or the configured default; raises `VectorStoreError` if none is configured. |
| `stores()` | Create and return every enabled store. |
| `names()` / `has(name)` / `default_name()` | Introspection. |
| `aclose()` | Close every created store, swallowing errors. |
| `available_store_types()` / `register_store` / `unregister_store` | Registry for built-in and custom store types. |

Switching backends means editing the configuration — application code never
changes.

### Managers

Three thin, backend-independent facades (`vectorstore/src/vectorstore/
managers.py`) that downstream code uses instead of calling the store directly:

- `CollectionManager` — `create` / `delete` / `list` / `info` / `stats`.
- `DocumentManager` — `add` / `update` / `delete` / `get` / `search` (builds a
  `SearchRequest` from kwargs).
- `MetadataManager` — `set` (merge-by-default, `merge=False` replaces) / `get` /
  `filter`.

## What was added

```
vectorstore/
├── pyproject.toml            # dist "openwrt-ai-vectorstore"; extra [faiss]
└── src/vectorstore/
    ├── __init__.py           # public exports
    ├── models.py             # VectorMetadata, VectorDocument, MetadataFilter,
    │                         #   SearchRequest, SearchResult, CollectionInfo,
    │                         #   CollectionStats, DEFAULT_NAMESPACE, …
    ├── errors.py             # VectorStoreError hierarchy
    ├── protocols.py          # VectorStore ABC (the contract)
    ├── config.py             # VectorStoreConfig, VectorStoresConfig
    ├── factory.py            # registry + VectorStoreFactory
    ├── managers.py           # CollectionManager, DocumentManager, MetadataManager
    └── backends/
        ├── _math.py          # pure-Python cosine similarity
        ├── _filters.py       # shared metadata filter matcher
        ├── _http.py          # VectorStoreHttpClient
        ├── sqlite.py         # SQLite reference backend
        ├── chroma.py         # Chroma REST adapter
        ├── qdrant.py         # Qdrant REST adapter
        └── faiss.py          # FAISS in-process backend (optional)
```

Tooling: `Makefile` `PY_PACKAGES` gained `./vectorstore`; `pyproject.toml`
ruff `src` and `known-first-party` gained `vectorstore`. No existing package
was modified.

## Tests

New suites (233 total, up from 166; all mocked transports, no network):

- `test_vector_models.py` — model defaults, metadata helpers, filter validation.
- `test_vector_store_conformance.py` — the behavioural contract run against
  **both** SQLite and FAISS: collection lifecycle, batch add/get, duplicate-id
  rejection, versioned upserts, delete counts, cosine ranking, filters,
  pagination, dimension mismatch, namespaces, missing-collection errors. This
  doubles as the specification for "the same API".
- `test_vector_sqlite.py` — persistence across store instances, connection
  error mapping.
- `test_vector_qdrant.py` / `test_vector_chroma.py` — stateful
  `httpx.MockTransport` emulations of the Qdrant / Chroma REST APIs proving the
  adapters' request/response mapping: create/duplicate/delete, add/get/delete,
  versioned upsert, search with cosine scores, namespace encoding, connection
  error normalization.
- `test_vector_faiss.py` — lazy-dependency guard, persistence across
  instances, index rebuild after update/delete.
- `test_vector_factory.py` — config validation, defaults, default/pinned
  resolution, registry, custom store types.
- `test_vector_managers.py` — manager delegation and namespace defaulting.

## Run

```bash
# offline reference backend (no dependencies)
python - <<'PY'
import asyncio
from vectorstore.config import VectorStoresConfig
from vectorstore.factory import VectorStoreFactory
from vectorstore.models import SearchRequest, VectorDocument

async def main():
    config = VectorStoresConfig.from_dict({
        "stores": {"sqlite": {}},  # or "qdrant" / "chroma" / "faiss"
    })
    factory = VectorStoreFactory(config)
    store = factory.get()
    await store.create_collection("docs", dimension=3)
    await store.add_documents("docs", [
        VectorDocument(id="a", vector=[1.0, 0.0, 0.0], text="alpha"),
        VectorDocument(id="b", vector=[0.0, 1.0, 0.0], text="beta"),
    ])
    results = await store.search("docs", SearchRequest(query_vector=[1.0, 0.0, 0.0], top_k=2))
    print([(r.id, r.score) for r in results])
    await factory.aclose()

asyncio.run(main())
PY
```

For FAISS: `pip install "openwrt-ai-vectorstore[faiss]"`.

## Roadmap note

This sprint delivers the storage capability. Retrieval, RAG wiring (the
`rag/` package remains a Sprint-1 stub), and knowledge-loader / chat grounding
remain later sprints — those will depend on `vectorstore` only, never on a
specific backend. The Sprint-6 `EmbeddingFactory` stays separate and will feed
vectors into the store in the RAG sprint.
