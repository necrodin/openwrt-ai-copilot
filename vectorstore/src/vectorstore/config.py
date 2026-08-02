"""Vector store configuration.

Stores are selected and configured entirely through configuration — never
through code. A ``vectorstores.yaml`` file (or an equivalent dict) defines
which store types are active, their endpoints/paths, and optional timeouts and
headers. The factory turns this configuration into store instances, so
switching from SQLite to Qdrant is a config change only.

Secrets are referenced by environment variable name (``api_key_env``); the key
value itself never lives in the configuration file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Default persistence locations per store type, applied when a config omits
#: ``path``. ``data/`` is git-ignored (see repository .gitignore).
DEFAULT_PATHS: dict[str, str] = {
    "sqlite": "data/vectorstore.sqlite3",
    "faiss": "data/vectorstore_faiss",
}

#: Default endpoints per HTTP store type, applied when a config omits
#: ``base_url``.
DEFAULT_BASE_URLS: dict[str, str] = {
    "qdrant": "http://localhost:6333",
    "chroma": "http://localhost:8000",
}

DEFAULT_STORE_TYPES: frozenset[str] = frozenset({"sqlite", "qdrant", "chroma", "faiss"})
SUPPORTED_STORE_TYPES = DEFAULT_STORE_TYPES

#: Store types that talk to a remote HTTP API.
HTTP_STORE_TYPES: frozenset[str] = frozenset({"qdrant", "chroma"})

#: Store types that persist to a local path.
PATH_STORE_TYPES: frozenset[str] = frozenset({"sqlite", "faiss"})


class VectorStoreConfig(BaseModel):
    """Configuration for a single vector store instance."""

    model_config = ConfigDict(extra="forbid")

    type: str
    name: str = ""
    enabled: bool = True

    path: str | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_ref: str | None = None
    extra_headers: dict[str, str] = Field(default_factory=dict)

    timeout_seconds: float = 30.0
    verify_tls: bool = True

    #: Namespace applied when a call does not pass one explicitly.
    default_namespace: str = "default"

    #: Chroma tenant/database (server-side isolation).
    tenant: str = "default"
    database: str = "default"

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        if value not in SUPPORTED_STORE_TYPES:
            raise ValueError(
                f"Unsupported vector store type {value!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_STORE_TYPES))}"
            )
        return value

    @field_validator("path")
    @classmethod
    def _validate_path(cls, value: str | None) -> str | None:
        if value == "":
            return None
        return value

    def effective_name(self) -> str:
        return self.name or self.type

    def effective_path(self) -> str:
        return self.path or DEFAULT_PATHS[self.type]

    def effective_base_url(self) -> str:
        return self.base_url or DEFAULT_BASE_URLS[self.type]


class VectorStoresConfig(BaseModel):
    """Top-level vector store configuration.

    ``default_store`` names the store to use when no store is pinned. Setting it
    to a different configured store switches the whole application's vector
    layer without any code change.
    """

    default_store: str | None = None
    stores: dict[str, VectorStoreConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _infer_store_types(cls, data: Any) -> Any:
        """Default each store's ``type`` to its config key."""
        if not isinstance(data, dict):
            return data
        stores = data.get("stores")
        if not isinstance(stores, dict):
            return data
        for key, entry in stores.items():
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("type")
            if entry_type is None:
                entry["type"] = key
            elif entry_type != key:
                raise ValueError(
                    f"Vector store entry {key!r} declares type {entry_type!r}; expected {key!r}"
                )
        return data

    @field_validator("default_store")
    @classmethod
    def _validate_default(cls, value: str | None) -> str | None:
        return value or None

    def enabled_stores(self) -> list[tuple[str, VectorStoreConfig]]:
        return [(name, cfg) for name, cfg in self.stores.items() if cfg.enabled]

    @classmethod
    def from_file(cls, path: str | Path) -> VectorStoresConfig:
        """Load configuration from a YAML or TOML file."""
        file_path = Path(path)
        text = file_path.read_text(encoding="utf-8")
        if file_path.suffix.lower() in (".yaml", ".yml"):
            import yaml

            data = yaml.safe_load(text) or {}
        elif file_path.suffix.lower() == ".toml":
            import tomllib

            data = tomllib.loads(text)
        else:
            raise ValueError("Unsupported config format; use .yaml, .yml or .toml")
        return cls.model_validate(data)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VectorStoresConfig:
        return cls.model_validate(data)


__all__ = [
    "DEFAULT_BASE_URLS",
    "DEFAULT_PATHS",
    "DEFAULT_STORE_TYPES",
    "HTTP_STORE_TYPES",
    "PATH_STORE_TYPES",
    "SUPPORTED_STORE_TYPES",
    "VectorStoreConfig",
    "VectorStoresConfig",
]
