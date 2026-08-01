"""Provider configuration tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from providers.config import (
    DEFAULT_BASE_URLS,
    SUPPORTED_PROVIDER_TYPES,
    ProviderConfig,
    ProvidersConfig,
)


def test_supported_types_matches_defaults() -> None:
    assert set(SUPPORTED_PROVIDER_TYPES) == set(DEFAULT_BASE_URLS)


def test_type_inferred_from_key() -> None:
    config = ProvidersConfig.model_validate({"providers": {"ollama": {"model": "qwen2.5:7b"}}})
    provider = config.providers["ollama"]
    assert provider.type == "ollama"


def test_explicit_type_must_match_key() -> None:
    with pytest.raises(ValidationError):
        ProvidersConfig.model_validate({"providers": {"ollama": {"type": "openai"}}})


def test_unknown_type_rejected() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(type="brand-new-llm")


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ProviderConfig(type="ollama", not_a_field=42)


def test_effective_base_url_falls_back_to_default() -> None:
    assert ProviderConfig(type="openai").effective_base_url() == DEFAULT_BASE_URLS["openai"]
    custom = ProviderConfig(type="openai", base_url="http://proxy:9000/v1")
    assert custom.effective_base_url() == "http://proxy:9000/v1"


def test_effective_name_falls_back_to_type() -> None:
    assert ProviderConfig(type="ollama").effective_name() == "ollama"
    named = ProviderConfig(type="ollama", name="homelab")
    assert named.effective_name() == "homelab"


def test_enabled_providers_filters_disabled(tmp_path: Path) -> None:
    config = ProvidersConfig.model_validate(
        {
            "default_provider": "ollama",
            "providers": {
                "ollama": {"enabled": True},
                "openai": {"enabled": False},
            },
        }
    )
    names = [name for name, _ in config.enabled_providers()]
    assert names == ["ollama"]
    assert config.default_provider == "ollama"


def test_from_file_yaml(tmp_path: Path) -> None:
    path = tmp_path / "providers.yaml"
    path.write_text(
        "default_provider: ollama\n"
        "providers:\n"
        "  ollama:\n"
        "    base_url: http://localhost:11434\n"
        "    model: qwen2.5:7b\n"
    )
    config = ProvidersConfig.from_file(path)
    assert config.default_provider == "ollama"
    assert config.providers["ollama"].model == "qwen2.5:7b"


def test_from_file_toml(tmp_path: Path) -> None:
    path = tmp_path / "providers.toml"
    path.write_text('[providers.ollama]\ntype = "ollama"\nmodel = "qwen2.5:7b"\n')
    config = ProvidersConfig.from_file(path)
    assert config.providers["ollama"].model == "qwen2.5:7b"


def test_from_file_unsupported_extension(tmp_path: Path) -> None:
    path = tmp_path / "providers.json"
    path.write_text("{}")
    with pytest.raises(ValueError):
        ProvidersConfig.from_file(path)
