"""VectorRetriever tests: embed -> search -> merge -> dedupe -> rank."""

from __future__ import annotations

import pytest

from rag.config import CollectionRef
from rag.errors import EmbeddingError, RetrieverError
from rag.retriever import VectorRetriever
from vectorstore.models import SearchResult, VectorMetadata


class FakeVectorStore:
    """Configurable fake over the ``vectorstore`` interface."""

    def __init__(self, results: dict | None = None) -> None:
        self.results = results or {}
        self.search_calls: list[tuple[str, str | None, int]] = []

    async def search(
        self, name: str, request, *, namespace: str | None = None
    ) -> list[SearchResult]:
        self.search_calls.append((name, namespace, request.top_k))
        return self.results.get((name, namespace), self.results.get(name, []))

    async def aclose(self) -> None:
        pass


def make_result(
    chunk_id: str,
    text: str,
    score: float,
    *,
    document_id: str | None = None,
    index: int | None = None,
    title: str = "Doc",
    **meta,
) -> SearchResult:
    values = {"document_id": document_id, "index": index, "title": title, **meta}
    return SearchResult(
        id=chunk_id,
        score=score,
        text=text,
        metadata=VectorMetadata(values={k: v for k, v in values.items() if v is not None}),
    )


def fake_embedder(vector: list[float]):
    async def embed(_text: str) -> list[float]:
        return vector

    return embed


def make_retriever(store: FakeVectorStore, **kwargs) -> VectorRetriever:
    return VectorRetriever(store, fake_embedder([0.1] * 8), **kwargs)


async def test_retrieve_ranks_by_normalized_score() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result("d1#0", "alpha firewall rules", 0.9, document_id="d1", index=0),
                make_result("d2#0", "beta wan interface", 0.7, document_id="d2", index=0),
                make_result("d3#0", "gamma logging", 0.55, document_id="d3", index=0),
            ]
        }
    )
    chunks = await make_retriever(store).retrieve("firewall rules", top_k=3)
    assert [chunk.id for chunk in chunks] == ["d1#0", "d2#0", "d3#0"]
    assert chunks[0].score == 1.0
    assert chunks[2].score == 0.0
    assert [chunk.rank for chunk in chunks] == [1, 2, 3]


async def test_top_k_caps_results() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result(
                    f"d{i}#0",
                    f"chunk number {i}",
                    1.0 - i * 0.1,
                    document_id=f"d{i}",
                    index=0,
                )
                for i in range(5)
            ]
        }
    )
    chunks = await make_retriever(store, default_top_k=2).retrieve("query")
    assert len(chunks) == 2
    assert chunks[-1].rank == 2


async def test_score_threshold_filters_low_results() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result("d1#0", "good match", 0.9, document_id="d1", index=0),
                make_result("d2#0", "weak match", 0.2, document_id="d2", index=0),
            ]
        }
    )
    chunks = await make_retriever(store, score_threshold=0.5).retrieve("query")
    assert [chunk.id for chunk in chunks] == ["d1#0"]


async def test_dedupe_by_id_keeps_highest_weighted_score() -> None:
    store = FakeVectorStore(
        {
            ("docs_a", "ns"): [
                make_result("d1#0", "text from a", 0.8, document_id="d1", index=0),
                make_result("d2#0", "unique a", 0.6, document_id="d2", index=0),
            ],
            ("docs_b", "ns"): [
                make_result("d1#0", "text from a", 0.9, document_id="d1", index=0),
                make_result("d3#0", "unique b", 0.4, document_id="d3", index=0),
            ],
        }
    )
    retriever = VectorRetriever(
        store,
        fake_embedder([0.1] * 8),
        collections=[
            CollectionRef(name="docs_a", namespace="ns", weight=1.0),
            CollectionRef(name="docs_b", namespace="ns", weight=1.0),
        ],
    )
    chunks = await retriever.retrieve("query", top_k=10)
    ids = [chunk.id for chunk in chunks]
    assert ids.count("d1#0") == 1
    assert set(ids) == {"d1#0", "d2#0", "d3#0"}


async def test_dedupe_by_text_drops_duplicate_content() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result("d1#0", "identical sentence here", 0.9, document_id="d1", index=0),
                make_result("d9#0", "  identical   sentence here", 0.8, document_id="d9", index=0),
                make_result("d2#0", "something else entirely", 0.7, document_id="d2", index=0),
            ]
        }
    )
    chunks = await make_retriever(store).retrieve("query", top_k=10)
    assert [chunk.id for chunk in chunks] == ["d1#0", "d2#0"]


async def test_dedupe_by_text_can_be_disabled() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result("d1#0", "identical sentence here", 0.9, document_id="d1", index=0),
                make_result("d9#0", "identical sentence here", 0.8, document_id="d9", index=0),
            ]
        }
    )
    chunks = await make_retriever(store, deduplicate_by_text=False).retrieve("query", top_k=10)
    assert len(chunks) == 2


async def test_missing_embedder_raises() -> None:
    store = FakeVectorStore({})
    retriever = VectorRetriever(store)
    with pytest.raises(EmbeddingError):
        await retriever.retrieve("query")


async def test_empty_query_raises() -> None:
    retriever = make_retriever(FakeVectorStore({}))
    with pytest.raises(RetrieverError):
        await retriever.retrieve("   ")


async def test_metadata_mapping_and_id_fallback() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result(
                    "doc-x#2", "with metadata", 0.8, document_id="doc-x", index=2, heading="Intro"
                ),
                SearchResult(
                    id="bare#5",
                    score=0.6,
                    text="no metadata",
                    metadata=VectorMetadata(),
                ),
            ]
        }
    )
    chunks = await make_retriever(store).retrieve("query", top_k=10)
    by_id = {chunk.id: chunk for chunk in chunks}
    assert by_id["doc-x#2"].document_id == "doc-x"
    assert by_id["doc-x#2"].index == 2
    assert by_id["doc-x#2"].heading == "Intro"
    assert by_id["bare#5"].document_id == "bare"
    assert by_id["bare#5"].index == 5


async def test_retrieve_documents_groups_by_document() -> None:
    store = FakeVectorStore(
        {
            "documents": [
                make_result(
                    "d1#0", "first chunk of one", 0.9, document_id="d1", index=0, title="T1"
                ),
                make_result("d1#1", "second chunk of one", 0.5, document_id="d1", index=1),
                make_result(
                    "d2#0", "only chunk of two", 0.7, document_id="d2", index=0, title="T2"
                ),
            ]
        }
    )
    documents = await make_retriever(store).retrieve_documents("query", top_k=10)
    assert [doc.document_id for doc in documents] == ["d1", "d2"]
    assert documents[0].chunk_count == 2
    assert documents[0].title == "T1"
    assert documents[0].best_score == 1.0


async def test_embeds_and_passes_namespace_and_filters() -> None:
    result = make_result("d1#0", "match", 0.5, document_id="d1", index=0)
    store = FakeVectorStore({"documents": [result]})
    retriever = VectorRetriever(
        store,
        fake_embedder([0.42, 0.58]),
        collections=[CollectionRef(name="documents", namespace="custom", weight=1.0)],
    )
    from vectorstore.models import MetadataFilter

    filter_ = MetadataFilter(field="lang", op="eq", value="en")
    chunks = await retriever.retrieve("query", top_k=3, filters=[filter_])
    assert len(chunks) == 1
    assert store.search_calls[0] == ("documents", "custom", 3)
    assert store.search_calls[0][2] == 3
    assert store.search_calls[0][1] == "custom"
    # embedder received the query
    assert store.search_calls


async def test_default_collection_and_namespace() -> None:
    result = make_result("d1#0", "match", 0.5, document_id="d1", index=0)
    store = FakeVectorStore({("documents", "default"): [result]})
    chunks = await make_retriever(store).retrieve("query")
    assert len(chunks) == 1
    assert store.search_calls[0][1] == "default"


async def test_aclose_delegates_to_store() -> None:
    store = FakeVectorStore({})
    closed = False

    async def close() -> None:
        nonlocal closed
        closed = True

    store.aclose = close  # type: ignore[method-assign]
    await make_retriever(store).aclose()
    assert closed
