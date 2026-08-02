"""Data model tests for the vector database layer."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from vectorstore.models import (
    DEFAULT_NAMESPACE,
    DISTANCE_COSINE,
    MetadataFilter,
    SearchRequest,
    VectorDocument,
    VectorMetadata,
)


def test_vector_metadata_helpers() -> None:
    metadata = VectorMetadata(values={"kind": "fruit", "size": 3})
    assert metadata.get("kind") == "fruit"
    assert metadata.get("missing", "fallback") == "fallback"
    assert metadata["size"] == 3
    assert metadata.to_dict() == {"kind": "fruit", "size": 3}


def test_vector_document_defaults() -> None:
    doc = VectorDocument(id="a", vector=[1.0, 0.0])
    assert doc.text == ""
    assert doc.metadata.values == {}
    assert doc.version == 1


def test_metadata_filter_default_op() -> None:
    clause = MetadataFilter(field="size", value=3)
    assert clause.op == "eq"


def test_metadata_filter_rejects_unknown_op() -> None:
    with pytest.raises(ValidationError):
        MetadataFilter(field="size", op="bogus", value=3)


def test_search_request_defaults() -> None:
    request = SearchRequest(query_vector=[1.0, 0.0])
    assert request.top_k == 10
    assert request.filters == []
    assert request.offset == 0
    assert request.limit is None
    assert request.include_vectors is False


def test_search_result_can_hold_vector() -> None:
    from vectorstore.models import SearchResult

    result = SearchResult(id="a", score=0.9, text="hi", vector=[1.0, 0.0], version=2)
    assert result.vector == [1.0, 0.0]
    assert result.version == 2


def test_constants() -> None:
    assert DEFAULT_NAMESPACE == "default"
    assert DISTANCE_COSINE == "cosine"
