"""Vector store factory and registry.

``VectorStoreFactory`` turns a :class:`VectorStoresConfig` into lazily-created,
fully-wired :class:`VectorStore` instances. Switching backends means editing the
configuration (changing ``default_store`` or a store's ``type``) — application
code never changes.
"""

from __future__ import annotations

import asyncio
from contextlib import suppress
from typing import Any

from vectorstore.config import VectorStoreConfig, VectorStoresConfig
from vectorstore.errors import VectorStoreError
from vectorstore.protocols import VectorStore

_FACTORIES: dict[str, type[VectorStore]] = {}


def _register_defaults() -> None:
    """Register every built-in store type (idempotent)."""
    from vectorstore.backends.chroma import ChromaVectorStore
    from vectorstore.backends.faiss import FAISSVectorStore
    from vectorstore.backends.qdrant import QdrantVectorStore
    from vectorstore.backends.sqlite import SQLiteVectorStore

    for cls in (
        SQLiteVectorStore,
        QdrantVectorStore,
        ChromaVectorStore,
        FAISSVectorStore,
    ):
        _FACTORIES.setdefault(cls.provider_type, cls)


def register_store(store_type: str, cls: type[VectorStore]) -> None:
    _FACTORIES[store_type] = cls


def unregister_store(store_type: str) -> None:
    _FACTORIES.pop(store_type, None)


def available_store_types() -> tuple[str, ...]:
    _register_defaults()
    return tuple(sorted(_FACTORIES))


def create_store(config: VectorStoreConfig, **overrides: Any) -> VectorStore:
    """Instantiate a store from its configuration.

    ``overrides`` are passed to the adapter constructor (used for dependency
    injection in tests, e.g. a mock HTTP client).
    """
    try:
        cls = _FACTORIES[config.type]
    except KeyError as exc:
        raise KeyError(f"Unknown vector store type: {config.type!r}") from exc
    return cls(config, **overrides)


class VectorStoreFactory:
    """Config-driven factory for :class:`VectorStore` instances.

    Stores are created lazily on first access and cached by name.
    """

    def __init__(
        self,
        config: VectorStoresConfig | None = None,
        *,
        store_overrides: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        self._config = config or VectorStoresConfig()
        self._overrides = store_overrides or {}
        self._stores: dict[str, VectorStore] = {}

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #

    def names(self) -> list[str]:
        return [name for name, _ in self._config.enabled_stores()]

    def has(self, name: str) -> bool:
        return name in self._config.stores

    def default_name(self) -> str | None:
        if self._config.default_store in self._config.stores:
            return self._config.default_store
        enabled = self.names()
        return enabled[0] if enabled else None

    @staticmethod
    def available_store_types() -> tuple[str, ...]:
        return available_store_types()

    # ------------------------------------------------------------------ #
    # Construction                                                       #
    # ------------------------------------------------------------------ #

    def stores(self) -> dict[str, VectorStore]:
        """Return all configured, enabled stores (creating them on demand)."""
        result: dict[str, VectorStore] = {}
        for name, cfg in self._config.enabled_stores():
            result[name] = self._get(name, cfg)
        return result

    def get(self, name: str | None = None) -> VectorStore:
        """Return a configured store by name (or the default when ``name`` is
        None). Raises :class:`VectorStoreError` if none is configured."""
        cfg = self._resolve(name)
        return self._get(cfg.effective_name(), cfg)

    def _get(self, name: str, cfg: VectorStoreConfig) -> VectorStore:
        if name not in self._stores:
            self._stores[name] = create_store(cfg, **self._overrides.get(name, {}))
        return self._stores[name]

    def _resolve(self, name: str | None) -> VectorStoreConfig:
        if name is not None:
            try:
                return self._config.stores[name]
            except KeyError as exc:
                raise VectorStoreError(f"Vector store {name!r} is not configured") from exc
        default = self.default_name()
        if default is None:
            raise VectorStoreError(
                "No vector store is configured. Add a store to your vectorstores.yaml "
                "or create a VectorStoresConfig with at least one enabled store."
            )
        return self._config.stores[default]

    async def aclose(self) -> None:
        """Close every created store, swallowing errors."""

        async def close(store: VectorStore) -> None:
            with suppress(Exception):  # noqa: BLE001 - close must never raise
                await store.aclose()

        await asyncio.gather(*(close(store) for store in self._stores.values()))


# Register built-in store types once at import time.
_register_defaults()


__all__ = [
    "VectorStoreFactory",
    "available_store_types",
    "create_store",
    "register_store",
    "unregister_store",
]
