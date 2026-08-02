"""Factory / config tests for the vector database layer."""

from __future__ import annotations

import pytest

from vectorstore.config import (
    DEFAULT_PATHS,
    DEFAULT_STORE_TYPES,
    VectorStoreConfig,
    VectorStoresConfig,
)
from vectorstore.errors import VectorStoreError
from vectorstore.factory import (
    VectorStoreFactory,
    available_store_types,
    create_store,
    register_store,
    unregister_store,
)
from vectorstore.protocols import VectorStore


def test_default_config_builds_empty_factory() -> None:
    factory = VectorStoreFactory()
    assert factory.names() == []
    assert factory.default_name() is None
    with pytest.raises(VectorStoreError):
        factory.get()


def test_config_from_dict() -> None:
    config = VectorStoresConfig.from_dict(
        {
            "default_store": "sqlite",
            "stores": {
                "sqlite": {"path": "data/t.sqlite3"},
                "qdrant": {},
            },
        }
    )
    assert config.default_store == "sqlite"
    assert config.stores["sqlite"].type == "sqlite"
    assert config.stores["sqlite"].effective_path() == "data/t.sqlite3"
    assert config.stores["qdrant"].effective_base_url() == "http://localhost:6333"


def test_config_type_must_match_key() -> None:
    with pytest.raises(ValueError):
        VectorStoresConfig.from_dict({"stores": {"local": {"type": "qdrant"}}})


def test_config_default_paths() -> None:
    assert DEFAULT_PATHS["sqlite"] == "data/vectorstore.sqlite3"
    assert DEFAULT_PATHS["faiss"] == "data/vectorstore_faiss"


def test_default_store_types() -> None:
    assert {"sqlite", "qdrant", "chroma", "faiss"} == DEFAULT_STORE_TYPES


def test_available_store_types() -> None:
    types = available_store_types()
    assert set(types) == {"sqlite", "qdrant", "chroma", "faiss"}


def test_factory_default_and_pinned(tmp_path) -> None:
    config = VectorStoresConfig.from_dict(
        {
            "default_store": "sqlite",
            "stores": {"sqlite": {"path": str(tmp_path / "a.db")}},
        }
    )
    factory = VectorStoreFactory(config)
    assert factory.names() == ["sqlite"]
    assert factory.default_name() == "sqlite"
    assert factory.has("sqlite") and not factory.has("other")
    store = factory.get()
    assert isinstance(store, VectorStore)
    assert store.name == "sqlite"
    assert factory.get("sqlite") is store


def test_factory_unknown_store_raises(tmp_path) -> None:
    config = VectorStoresConfig.from_dict({"stores": {"sqlite": {"path": str(tmp_path / "a.db")}}})
    factory = VectorStoreFactory(config)
    with pytest.raises(VectorStoreError):
        factory.get("nope")


def test_create_store_overrides(tmp_path) -> None:
    config = VectorStoreConfig(type="sqlite", path=str(tmp_path / "b.db"))
    store = create_store(config)
    assert store.provider_type == "sqlite"
    assert store.default_namespace == "default"


def test_register_and_unregister() -> None:
    class Dummy(VectorStore):
        provider_type = "dummy"

        def __init__(self, config, **kwargs) -> None:
            self.name = "dummy"
            self.default_namespace = "default"

        async def health(self) -> bool:
            return True

        async def aclose(self) -> None:
            pass

        async def create_collection(self, name, **kwargs):
            raise NotImplementedError

        async def delete_collection(self, name, **kwargs):
            raise NotImplementedError

        async def list_collections(self, **kwargs):
            return []

        async def collection_info(self, name, **kwargs):
            return None

        async def stats(self, name, **kwargs):
            raise NotImplementedError

        async def add_documents(self, name, documents, **kwargs):
            return []

        async def update_documents(self, name, documents, **kwargs):
            return 0

        async def delete_documents(self, name, ids, **kwargs):
            return 0

        async def get_documents(self, name, ids, **kwargs):
            return []

        async def search(self, name, request, **kwargs):
            return []

        async def filter_documents(self, name, filters, **kwargs):
            return []

        async def set_metadata(self, name, id, metadata, **kwargs):
            return None

        async def get_metadata(self, name, id, **kwargs):
            from vectorstore.models import VectorMetadata

            return VectorMetadata()

    register_store("dummy", Dummy)
    try:
        assert "dummy" in available_store_types()
        config = VectorStoreConfig.model_construct(type="dummy")
        assert isinstance(create_store(config), Dummy)
    finally:
        unregister_store("dummy")
    assert "dummy" not in available_store_types()
