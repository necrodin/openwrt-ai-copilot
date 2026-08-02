"""Knowledge platform configuration.

The knowledge platform is configured entirely through configuration — which
source, which chunk strategy, which indexer — never through code. A
``knowledge.yaml`` file (or equivalent dict) defines collections; each
collection names a source and can override the chunking defaults.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Default chunk strategy, applied when a collection does not override it.
DEFAULT_CHUNK_STRATEGY = "fixed"
DEFAULT_CHUNK_SIZE = 500
DEFAULT_OVERLAP = 100

#: Supported chunk strategy names (matches ChunkStrategy.strategy_type).
SUPPORTED_CHUNK_STRATEGIES = frozenset({"fixed", "sliding", "heading", "paragraph"})

#: Supported source types.
SUPPORTED_SOURCE_TYPES = frozenset({"openwrt", "filesystem", "static"})

#: Supported indexer types.
SUPPORTED_INDEXER_TYPES = frozenset({"memory", "filesystem"})


class ChunkingConfig(BaseModel):
    """Chunking behaviour for a collection (or the whole platform)."""

    model_config = ConfigDict(extra="forbid")

    strategy: str = DEFAULT_CHUNK_STRATEGY
    chunk_size: int = DEFAULT_CHUNK_SIZE
    overlap: int | None = None

    @field_validator("strategy")
    @classmethod
    def _validate_strategy(cls, value: str) -> str:
        if value not in SUPPORTED_CHUNK_STRATEGIES:
            raise ValueError(
                f"Unsupported chunk strategy {value!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_CHUNK_STRATEGIES))}"
            )
        return value

    @field_validator("chunk_size")
    @classmethod
    def _validate_size(cls, value: int) -> int:
        return max(1, value)


class KnowledgeCollectionConfig(BaseModel):
    """One named collection to build from a source."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source: str
    description: str = ""
    #: Optional topic filter for the OpenWrt source.
    topics: list[str] | None = None
    #: Optional pattern/format filter for filesystem sources.
    pattern: str | None = None
    formats: list[str] | None = None
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    enabled: bool = True

    def effective_chunking(self) -> ChunkingConfig:
        return self.chunking


class KnowledgePlatformConfig(BaseModel):
    """Top-level knowledge platform configuration."""

    model_config = ConfigDict(extra="forbid")

    indexer_type: str = "memory"
    indexer_path: str = "data/knowledge_index"
    chunking: ChunkingConfig = Field(default_factory=ChunkingConfig)
    collections: list[KnowledgeCollectionConfig] = Field(default_factory=list)

    @field_validator("indexer_type")
    @classmethod
    def _validate_indexer(cls, value: str) -> str:
        if value not in SUPPORTED_INDEXER_TYPES:
            raise ValueError(
                f"Unsupported indexer type {value!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_INDEXER_TYPES))}"
            )
        return value

    @classmethod
    def from_file(cls, path: str | Path) -> KnowledgePlatformConfig:
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
    def from_dict(cls, data: dict[str, Any]) -> KnowledgePlatformConfig:
        return cls.model_validate(data)


__all__ = [
    "ChunkingConfig",
    "DEFAULT_CHUNK_SIZE",
    "DEFAULT_CHUNK_STRATEGY",
    "DEFAULT_OVERLAP",
    "KnowledgeCollectionConfig",
    "KnowledgePlatformConfig",
    "SUPPORTED_CHUNK_STRATEGIES",
    "SUPPORTED_INDEXER_TYPES",
    "SUPPORTED_SOURCE_TYPES",
]
