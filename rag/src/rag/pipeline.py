"""RAG orchestration pipeline.

Sprint 1 stub: defines the interface. The real implementation lands in Sprint 3
and composes chunking, embedding (via `ai.core`), retrieval, and reranking.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class RetrievedChunk:
    document_id: str
    index: int
    text: str
    score: float


class RAGPipeline:
    """Orchestrates ingest -> embed -> retrieve -> rerank for one knowledge base."""

    def __init__(self, knowledge_base_id: str) -> None:
        self.knowledge_base_id = knowledge_base_id

    def ingest(self, documents: list[str]) -> int:
        """Ingest documents and return the number of chunks stored."""
        raise NotImplementedError("Sprint 3")

    def search(self, query: str, top_k: int = 8) -> list[RetrievedChunk]:
        """Retrieve the most relevant chunks for a query."""
        raise NotImplementedError("Sprint 3")
