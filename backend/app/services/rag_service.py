"""RAG chat service: grounded, cited answers over the Retrieval Core + providers.

The service owns the shared, persistent retrieval stack (vector store, embedder
with its cache, reranker, retrieval/prompt cache) and exposes per-conversation
:class:`RAGEngine` instances so conversation memory survives across requests.

RAG chat is opt-in: it is loaded from ``rag.yaml`` during startup. When the
config file is missing (or fails to load), the app keeps the existing
router-state chat path unchanged.
"""

from __future__ import annotations

import logging
from contextlib import suppress
from pathlib import Path

from app.core.config import settings
from providers.embedding import EmbeddingFactory
from providers.factory import ProviderManager
from rag.ai import (
    CachedEmbedder,
    RAGConfiguration,
    RAGEngine,
    build_memory,
    build_reranker,
    build_retrieval_config,
)
from rag.ai.cache import EmbeddingCache
from rag.cache import InMemoryContextCache
from rag.config import CacheConfig
from rag.engine import RetrievalEngine
from rag.protocols import Retriever
from rag.retriever import VectorRetriever
from vectorstore.backends.sqlite import SQLiteVectorStore
from vectorstore.config import VectorStoreConfig
from vectorstore.errors import CollectionExistsError

logger = logging.getLogger(__name__)


class RAGService:
    """Composes the shared retrieval stack and per-session RAG engines."""

    def __init__(
        self,
        manager: ProviderManager,
        configuration: RAGConfiguration,
        vector_store: SQLiteVectorStore,
        embedder: CachedEmbedder,
        retriever: Retriever,
    ) -> None:
        self._manager = manager
        self.config = configuration
        self._vector_store = vector_store
        self._embedder = embedder
        self._retriever = retriever
        self._reranker = build_reranker(manager, configuration)
        self._cache = InMemoryContextCache(CacheConfig(enabled=configuration.use_cache))
        self._retrieval_engines: dict[tuple[str, str], RetrievalEngine] = {}

    @classmethod
    async def create(
        cls,
        manager: ProviderManager,
        configuration: RAGConfiguration,
        *,
        vector_store_path: str,
    ) -> RAGService:
        """Build the service: vector store, collection, embedder, retriever."""
        store = SQLiteVectorStore(
            VectorStoreConfig(
                type="sqlite",
                path=vector_store_path,
                name=configuration.collection,
            )
        )
        namespace = configuration.namespace or store.default_namespace
        info = await store.collection_info(configuration.collection, namespace=namespace)
        if info is None:
            with suppress(CollectionExistsError):  # racing creators
                await store.create_collection(
                    configuration.collection,
                    dimension=configuration.vector_dimensions,
                    namespace=namespace,
                )

        embedding = EmbeddingFactory(manager)
        embedder = CachedEmbedder(
            embedding,
            EmbeddingCache(),
            preferred=configuration.embed_provider,
            model=configuration.embed_model,
        )
        retrieval_config = build_retrieval_config(configuration)
        retriever = VectorRetriever(
            store,
            embedder,
            collections=retrieval_config.collections,
            default_top_k=configuration.top_k,
            score_threshold=configuration.score_threshold,
        )
        return cls(manager, configuration, store, embedder, retriever)

    # ------------------------------------------------------------------ #
    # Per-conversation engines                                           #
    # ------------------------------------------------------------------ #

    def _retrieval_engine(self, subject: str, session_id: str) -> RetrievalEngine:
        """The retrieval engine for one ``(subject, session_id)`` conversation.

        Engines (with their conversation memory) are namespaced by the
        authenticated principal, so two users never share RAG memory even when
        they happen to submit the same client-visible ``session_id``.
        """
        key = (subject, session_id)
        engine = self._retrieval_engines.get(key)
        if engine is None:
            engine = RetrievalEngine(
                self._retriever,
                memory=build_memory(self.config),
                cache=self._cache,
                reranker=self._reranker,
                config=build_retrieval_config(self.config),
            )
            self._retrieval_engines[key] = engine
        return engine

    def engine_for(self, subject: str, session_id: str, provider) -> RAGEngine:
        """A RAG engine bound to one conversation, one principal, one provider."""
        return RAGEngine(
            self._retriever,
            configuration=self.config,
            retrieval_engine=self._retrieval_engine(subject, session_id),
            reranker=self._reranker,
            provider=provider,
        )

    def seed_history(self, subject: str, session_id: str, turns: list[tuple[str, str]]) -> None:
        """Replay persisted turns into the session's memory when it is empty.

        Only seeds an uninitialised conversation, so restarting the backend does
        not lose the durable SQLite history for a session. Memory is namespaced
        by ``subject`` so a user can never inherit another user's context.
        """
        engine = self._retrieval_engine(subject, session_id)
        memory = engine.memory
        if memory is None or memory.state(session_id) is not None:
            return
        for role, content in turns:
            if role in ("user", "assistant") and content:
                memory.add(session_id, role, content)

    async def aclose(self) -> None:
        """Release the vector store."""
        await self._vector_store.aclose()


async def load_rag_service(manager: ProviderManager) -> RAGService | None:
    """Load the RAG service from ``rag.yaml``; ``None`` disables RAG chat."""
    path = Path(settings.rag_config_file)
    if not path.exists():
        return None
    try:
        configuration = RAGConfiguration.from_file(path)
    except Exception as exc:  # noqa: BLE001 - a bad config disables RAG, not the app
        logger.error("Failed to load RAG configuration from %s: %s", path, exc)
        return None
    try:
        return await RAGService.create(
            manager,
            configuration,
            vector_store_path=settings.rag_vector_store_path,
        )
    except Exception as exc:  # noqa: BLE001 - startup must never fail on RAG
        logger.error("Failed to initialise RAG service: %s", exc)
        return None
