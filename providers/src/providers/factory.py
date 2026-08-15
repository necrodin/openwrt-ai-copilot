"""Provider factory and manager.

``create_provider_manager()`` turns a :class:`ProvidersConfig` into a
:class:`ProviderManager` whose providers are fully wired. Switching providers
means editing the configuration file (e.g. changing ``default_provider`` or
``base_url``) — the application code never changes.
"""

from __future__ import annotations

from functools import partial
from typing import Any

from ai.core.registry import registry
from providers.base import BaseProvider
from providers.config import ProviderConfig, ProvidersConfig

_FACTORIES: dict[str, type[BaseProvider]] = {}


def _register_defaults() -> None:
    """Register every built-in provider type (idempotent)."""
    from providers.compat_cloud import (
        AnthropicProvider,
        AzureOpenAIProvider,
        CerebrasProvider,
        CohereProvider,
        CompatProvider,
        DeepSeekProvider,
        FireworksProvider,
        GeminiProvider,
        GroqProvider,
        MistralProvider,
        PerplexityProvider,
        TogetherProvider,
        XAIProvider,
    )
    from providers.lmstudio import LMStudioProvider
    from providers.nim import NIMProvider
    from providers.nv_embed import NVEmbedProvider
    from providers.ollama import OllamaProvider
    from providers.openai import OpenAIProvider
    from providers.openrouter import OpenRouterProvider
    from providers.vllm import VLLMProvider

    for cls in (
        OllamaProvider,
        NIMProvider,
        NVEmbedProvider,
        OpenAIProvider,
        OpenRouterProvider,
        LMStudioProvider,
        VLLMProvider,
        CompatProvider,
        AzureOpenAIProvider,
        AnthropicProvider,
        GeminiProvider,
        TogetherProvider,
        GroqProvider,
        DeepSeekProvider,
        MistralProvider,
        XAIProvider,
        CohereProvider,
        PerplexityProvider,
        FireworksProvider,
        CerebrasProvider,
    ):
        _FACTORIES.setdefault(cls.provider_type, cls)


def register_provider(provider_type: str, cls: type[BaseProvider]) -> None:
    _FACTORIES[provider_type] = cls


def unregister_provider(provider_type: str) -> None:
    _FACTORIES.pop(provider_type, None)


def available_provider_types() -> tuple[str, ...]:
    _register_defaults()
    return tuple(sorted(_FACTORIES))


def create_provider(config: ProviderConfig, **overrides: Any) -> BaseProvider:
    """Instantiate a provider from its configuration.

    ``overrides`` are passed to the adapter constructor (used for dependency
    injection in tests, e.g. a mock transport).
    """
    try:
        cls = _FACTORIES[config.type]
    except KeyError as exc:
        raise KeyError(f"Unknown provider type: {config.type!r}") from exc
    return cls(config, **overrides)


class ProviderManager:
    """Holds the configured, ready-to-use providers."""

    def __init__(
        self,
        providers: dict[str, BaseProvider],
        *,
        default_provider: str | None = None,
    ) -> None:
        self._providers = providers
        self.default_name = default_provider if default_provider in providers else None
        self._register_capabilities()

    @property
    def providers(self) -> dict[str, BaseProvider]:
        return self._providers

    def get_provider(self, name: str) -> BaseProvider:
        try:
            return self._providers[name]
        except KeyError as exc:
            raise KeyError(f"Provider {name!r} is not configured") from exc

    def all(self) -> list[BaseProvider]:
        return list(self._providers.values())

    def names(self) -> list[str]:
        return list(self._providers)

    def default(self) -> BaseProvider | None:
        if self.default_name is None:
            return None
        return self._providers[self.default_name]

    def get_for_capability(
        self,
        capability: str,
        *,
        preferred: str | None = None,
    ) -> BaseProvider | None:
        """Pick a provider for a capability without probing the network.

        Preference order: explicitly preferred name, the configured default,
        then any configured provider that statically declares the capability.
        """
        ordered: list[str] = []
        if preferred:
            ordered.append(preferred)
        if self.default_name and self.default_name not in ordered:
            ordered.append(self.default_name)
        ordered.extend(name for name in self._providers if name not in ordered)

        for name in ordered:
            provider = self._providers[name]
            if capability in provider.static_capabilities():
                return provider
        return None

    async def health(self) -> dict[str, bool]:
        import asyncio

        async def check(name: str, provider: BaseProvider) -> tuple[str, bool]:
            try:
                return name, await provider.health()
            except Exception:  # noqa: BLE001 - health must never raise
                return name, False

        results = await asyncio.gather(
            *(check(name, provider) for name, provider in self._providers.items())
        )
        return dict(results)

    async def aclose(self) -> None:
        import asyncio

        await asyncio.gather(*(provider.aclose() for provider in self._providers.values()))

    def _register_capabilities(self) -> None:
        """Expose provider capabilities to the global capability registry."""
        for name, provider in self._providers.items():
            for capability in provider.static_capabilities():
                registry.register(
                    capability,
                    name,
                    partial(create_provider, provider.config),
                )


def create_provider_manager(config: ProvidersConfig) -> ProviderManager:
    providers = {name: create_provider(cfg) for name, cfg in config.enabled_providers()}
    return ProviderManager(providers, default_provider=config.default_provider)


# Register built-in provider types once at import time.
_register_defaults()


__all__ = [
    "ProviderManager",
    "available_provider_types",
    "create_provider",
    "create_provider_manager",
    "register_provider",
    "unregister_provider",
]
