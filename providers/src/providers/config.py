"""Provider configuration.

Providers are selected and configured entirely through configuration — never
through code. A ``providers.yaml`` file (or an equivalent dict) defines which
provider types are active, their endpoints, model defaults, and optional
capability overrides. The factory turns this configuration into provider
instances, so switching from Ollama to OpenAI is a config change only.

Secrets are referenced by environment variable name (``api_key_env``); the key
value itself never lives in the configuration file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Default endpoints per provider type, applied when a provider config omits
#: ``base_url``.
DEFAULT_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434",
    "nim": "https://integrate.api.nvidia.com/v1",
    "nvembed": "https://integrate.api.nvidia.com/v1",
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "lmstudio": "http://localhost:1234/v1",
    "vllm": "http://localhost:8000/v1",
}

SUPPORTED_PROVIDER_TYPES = frozenset(DEFAULT_BASE_URLS)


class ProviderConfig(BaseModel):
    """Configuration for a single provider instance."""

    model_config = ConfigDict(extra="forbid")

    type: str
    name: str = ""
    enabled: bool = True

    base_url: str | None = None
    api_key_env: str | None = None
    api_key_ref: str | None = None

    model: str = ""
    embed_model: str = ""
    vision_model: str = ""
    rerank_model: str = ""
    embed_dimensions: int | None = None
    #: Maximum number of inputs per embeddings HTTP call for this provider.
    #: The embedding platform splits larger batches automatically.
    embed_batch_size: int | None = None

    timeout_seconds: float = 60.0
    verify_tls: bool = True
    extra_headers: dict[str, str] = Field(default_factory=dict)

    #: Explicit capability override. When set, capability detection is bypassed
    #: and this exact set is reported. Use to force a capability on/off.
    capabilities: set[str] | None = None

    cost_per_1k_prompt: float = 0.0
    cost_per_1k_completion: float = 0.0

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: str) -> str:
        if value not in SUPPORTED_PROVIDER_TYPES:
            raise ValueError(
                f"Unsupported provider type {value!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_PROVIDER_TYPES))}"
            )
        return value

    def effective_name(self) -> str:
        return self.name or self.type

    def effective_base_url(self) -> str:
        return self.base_url or DEFAULT_BASE_URLS[self.type]


class ProvidersConfig(BaseModel):
    """Top-level provider configuration.

    ``default_provider`` names the provider to use for calls that do not pin a
    provider explicitly. Setting it to a different configured provider switches
    the whole application's AI backend without any code change.
    """

    default_provider: str | None = None
    providers: dict[str, ProviderConfig] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _infer_provider_types(cls, data: Any) -> Any:
        """Default each provider's ``type`` to its config key.

        ``providers: {ollama: {...}}`` means type ``ollama``; an explicit type
        must match the key, which keeps the config unambiguous.
        """
        if not isinstance(data, dict):
            return data
        providers = data.get("providers")
        if not isinstance(providers, dict):
            return data
        for key, entry in providers.items():
            if not isinstance(entry, dict):
                continue
            entry_type = entry.get("type")
            if entry_type is None:
                entry["type"] = key
            elif entry_type != key:
                raise ValueError(
                    f"Provider entry {key!r} declares type {entry_type!r}; expected {key!r}"
                )
        return data

    @field_validator("default_provider")
    @classmethod
    def _validate_default(cls, value: str | None) -> str | None:
        return value or None

    def enabled_providers(self) -> list[tuple[str, ProviderConfig]]:
        return [(name, cfg) for name, cfg in self.providers.items() if cfg.enabled]

    @classmethod
    def from_file(cls, path: str | Path) -> ProvidersConfig:
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


__all__ = [
    "DEFAULT_BASE_URLS",
    "ProvidersConfig",
    "ProviderConfig",
    "SUPPORTED_PROVIDER_TYPES",
]
