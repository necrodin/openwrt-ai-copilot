# Sprint 8 — Provider-Independent Knowledge Platform

Status: **complete** (verification: 402 pytest passed — 233 prior + 169 new —
ruff clean; no network).

## Goal

A knowledge platform that turns documentation into chunked, versioned,
metadata-rich documents — independent of any AI provider, vector store, or
downstream RAG. The platform ingests 7 text formats (Markdown, HTML, PDF, TXT,
JSON, YAML, XML) from 3 source kinds (OpenWrt catalog, local filesystem,
in-memory) through one pipeline:

```
source → loader → parser → extractor → chunker → indexer
```

No Retrieval, no AI Chat, no LLM calls. Everything is an interface registered
in `KnowledgeRegistry`; any step can be swapped through configuration, never
code.

## Design decisions

### One pipeline, every step an interface

`knowledge/src/knowledge/protocols.py` defines the contract for every stage:

| Interface | Responsibility |
|---|---|
| `KnowledgeSource` | List/load document references (catalog). |
| `KnowledgeLoader` | Fetch raw bytes for a reference (file / directory / HTTP / in-memory). |
| `KnowledgeParser` | Turn raw bytes of one format into a normalized `KnowledgeDocument`. |
| `ChunkStrategy` | Split a document into deterministic `KnowledgeChunk`s. |
| `MetadataExtractor` | Derive `KnowledgeMetadata` from a document. |
| `KnowledgeIndexer` | Store documents/chunks incrementally with version + duplicate tracking. |

Everything is registered in `KnowledgeRegistry`
(`knowledge/src/knowledge/registry.py`) — thread-safe, with
`register_builtins()` idempotently registering every shipped implementation and
**never** replacing user-registered components with the same key.

### Models (`knowledge/src/knowledge/models.py`)

- `KnowledgeMetadata` — dict-like arbitrary key/value store with `get` / `to_dict`
  / `merge` / `keys` / `items` / `__contains__`.
- `KnowledgeDocument` — id (stable sha1 of `format:source:reference`), source,
  reference, format, title, normalized `text`, language, metadata, `checksum`,
  `version`, `created_at`.
- `KnowledgeChunk` — id `<document_id>#<index>` (deterministic for diffing),
  heading, text, checksum.
- `KnowledgeCollection` — named corpus: document ids, `chunk_count`, version.
- `KnowledgeVersion` — one pass outcome per document (`change` is one of
  `added` / `updated` / `unchanged` / `removed` / `duplicate`).
- `IndexResult` — aggregate run outcome; `.changed` is true when anything was
  added / updated / removed.

### Incremental indexing via checksums

`knowledge/src/knowledge/checksum.py` + `normalization.py`:

- `normalize_text` — NFC, control-char strip, whitespace collapse, paragraph
  breaks preserved as single blank lines.
- `canonical_text` — normalized, lowercased, punctuation-stripped, one line;
  used **only** for comparisons.
- `document_checksum` — sha256 over canonical text, so formatting-only changes
  never count as content changes.

Each ingest pass decides per document: **added** (id unseen), **updated**
(checksum changed, version bumped), **unchanged** (same checksum, not
re-written), **duplicate** (checksum owned by a *different* id — not stored),
and `reconcile` reports **removed** (known id missing from a later pass).

### Chunk strategies (`knowledge/src/knowledge/chunking.py`)

- `fixed` — word-count splits, no overlap.
- `sliding` — overlapping windows (default overlap = half the window).
- `heading` — splits at heading offsets (from parser metadata `headings`);
  oversized sections re-split; falls back to `fixed` without headings.
- `paragraph` — splits on blank lines; merges short adjacent paragraphs;
  oversized paragraphs re-split.

Chunk sizes/overlap are configurable (defaults: fixed @ 500; built-in registry
chunkers @ 300).

### Parsers (`knowledge/src/knowledge/parsers/`)

| Format | Notes |
|---|---|
| `markdown` | YAML front-matter → metadata; headings with char offsets into the normalized text; link/image/emphasis stripping. |
| `html` | stdlib `HTMLParser`: title, headings, visible text; script/style skipped. |
| `txt` | Plain text, normalized. |
| `json` | `text`/`content`/`body` strings, `sections` lists, or fallback pretty-printed JSON; other keys → metadata. |
| `yaml` | `safe_load`, reuses the JSON extractor; plain strings / parse failures fall back to raw text. |
| `xml` | ElementTree walk; title/metadata tags; `key`/`list` attributes → metadata. |
| `pdf` | Lazy `pypdf` (`[pdf]` extra), mirroring the FAISS lazy-dependency pattern; clear error when missing. |

### Loaders & sources

- Loaders: `TextLoader` (in-memory), `FileLoader`, `DirectoryLoader`
  (glob, references relative to root), `HttpLoader` (httpx, injectable client —
  tests use `MockTransport`; async-only).
- Sources: `OpenWrtKnowledgeSource` (catalog of the 12 OpenWrt knowledge
  domains — wiki, LuCI, WireGuard, OpenVPN, nftables, iptables, dnsmasq,
  odhcpd, SQM, mwan3, UCI, package docs — each with reference material,
  packages, UCI config files, tags), `FileSystemSource` (extension → format),
  `StaticSource` (in-memory, ideal for tests/snippets).

### Language detection (`knowledge/src/knowledge/language.py`)

Pure-Python, no external deps: Unicode block script detection + per-language
stop-word scoring. Returns ISO 639-1 codes (`en`, `fr`, `de`, `es`, `pt`,
`nl`, `it`, `ru`, `zh`, `ar`, `el`, …) with an honest `"unknown"` fallback for
short/uninformative text.

### Configuration & manager

- `knowledge/src/knowledge/config.py` — `ChunkingConfig` (strategy/size/overlap,
  validated against `SUPPORTED_CHUNK_STRATEGIES`), `KnowledgeCollectionConfig`
  (source, topic/format/pattern filters, chunking override, enabled),
  `KnowledgePlatformConfig` (indexer type + path, chunking defaults,
  collections; loads from YAML/TOML via `from_file` or dict via `from_dict`).
- `knowledge/src/knowledge/manager.py` — `KnowledgeManager` composes
  registry + config into the end-to-end pipeline:
  `index_collection(collection_id)` → `IndexResult`, `index_all()`,
  `documents` / `chunks` / `collection(s)` / `find_duplicates` / `versions`.

### Indexers (`knowledge/src/knowledge/indexer.py`)

- `InMemoryKnowledgeIndexer` — default; state in memory.
- `FileSystemKnowledgeIndexer` — one JSON file per collection under a root,
  enabling true incremental indexing across process runs (loaded at init;
  empty root behaves like the in-memory indexer).

## What was added

```
knowledge/
├── pyproject.toml            # dist "openwrt-ai-knowledge"; extra [pdf] = pypdf
└── src/knowledge/
    ├── __init__.py           # public exports, __version__ = 0.4.0-alpha
    ├── models.py             # KnowledgeDocument/Chunk/Collection/Metadata/Version,
    │                         #   IndexResult, KnowledgeChange
    ├── errors.py             # KnowledgeError hierarchy + UnsupportedFormatError
    ├── protocols.py          # KnowledgeSource/Loader/Parser/ChunkStrategy/
    │                         #   MetadataExtractor/KnowledgeIndexer ABCs
    ├── registry.py           # KnowledgeRegistry + register_builtins/clear
    ├── checksum.py           # sha256_hex, document_checksum, chunk_checksum
    ├── normalization.py      # normalize_text, canonical_text
    ├── language.py           # pure-Python detect_language
    ├── chunking.py           # fixed / sliding / heading / paragraph strategies
    ├── extractors.py         # title / headings / language / source / stats / composite
    ├── loaders.py            # Text / File / Directory / Http loaders
    ├── config.py             # ChunkingConfig, KnowledgeCollectionConfig,
    │                         #   KnowledgePlatformConfig
    ├── manager.py            # KnowledgeManager facade
    ├── indexer.py            # InMemory + FileSystem indexers
    ├── parsers/              # _base + markdown/html/txt/json/yaml/xml/pdf
    └── sources/              # openwrt (12-topic catalog) + filesystem + static
```

Tooling: `Makefile` `PY_PACKAGES` gained `./knowledge`; `pyproject.toml`
ruff `src` and `known-first-party` gained `knowledge`; `pip install -e ./knowledge`
verified. `rag/`, `vectorstore/`, `ai/`, `providers/` untouched — the platform
imports none of them.

## Tests

New suites (169 tests, raising the suite from 233 to 402; no network — the
HTTP loader runs against `httpx.MockTransport`):

- `test_knowledge_models.py` — metadata helpers, document/chunk/collection/
  version defaults, `IndexResult.changed`, JSON round-trip.
- `test_knowledge_normalization.py` — whitespace/newline/control-char handling,
  NFC, paragraph preservation, canonical form, checksum stability.
- `test_knowledge_language.py` — parametrized detection across 12 languages,
  unknown fallback, markup robustness.
- `test_knowledge_chunking.py` — fixed/sliding/heading/paragraph behaviour,
  deterministic ids, oversize re-splitting, merging, fallbacks.
- `test_knowledge_parsers.py` — every format, incl. PDF lazy-guard + error
  wrapping, YAML plain-string/parse-failure fallbacks, stable document ids.
- `test_knowledge_extractors.py` — each extractor + composite override order.
- `test_knowledge_indexer.py` — parametrized against memory AND filesystem:
  add/unchanged/updated/duplicate, reconcile, versions, find_duplicates,
  chunk totals, filesystem persistence across instances, corrupt-state error.
- `test_knowledge_loaders.py` — text/file/directory loaders; HTTP loader via
  MockTransport (async success, sync-error, 500 wrapping, client ownership).
- `test_knowledge_sources.py` — 12-topic OpenWrt catalog (fields, scoping,
  unknown-topic error), filesystem source (relative refs, format inference),
  static source.
- `test_knowledge_registry.py` — register/get/duplicate/replace, builtins
  idempotence + user-preservation, case-insensitive parser lookup,
  `UnsupportedFormatError`, clear/unregister.
- `test_knowledge_config.py` — defaults, validation, `from_dict`, `from_file`
  (YAML/TOML), unknown extension, extra-field rejection.
- `test_knowledge_manager.py` — end-to-end pipeline: add/incremental/update/
  remove/duplicate, format filtering, `index_all` disable, filesystem indexer
  persistence across managers, topic-reference filtering, introspection.

## Run

```bash
# Build a knowledge collection from in-memory documents
python - <<'PY'
import asyncio
from knowledge import KnowledgeManager, KnowledgePlatformConfig
from knowledge.registry import KnowledgeRegistry
from knowledge.sources import StaticSource

async def main():
    registry = KnowledgeRegistry()
    registry.register_builtins()
    registry.register_source(StaticSource("static", {
        "wireguard.md": "# WireGuard\n\nWireGuard is a fast, modern VPN tunnel.",
    }, format="markdown"), replace=True)

    config = KnowledgePlatformConfig.from_dict({
        "collections": [{"id": "vpn", "source": "static"}],
    })
    manager = KnowledgeManager(registry, config)
    result = await manager.index_collection("vpn")
    print(result.model_dump())
    for doc in manager.documents("vpn"):
        print(doc.id, doc.language, doc.metadata.to_dict())

asyncio.run(main())
PY
```

For PDFs: `pip install "openwrt-ai-knowledge[pdf]"`.

## Roadmap note

This sprint delivers knowledge ingestion. Retrieval (embeddings + the Sprint-7
`vectorstore`), RAG wiring (`rag/` remains a Sprint-1 stub), and chat grounding
are later sprints — they will consume `knowledge` documents/chunks and the
`vectorstore` interface only, never a specific backend or provider.
