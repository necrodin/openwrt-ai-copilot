"""Provider manager lifecycle and request-scoped access."""

from __future__ import annotations

from pathlib import Path

from fastapi import Request

from app.core.config import settings
from providers.config import ProvidersConfig
from providers.factory import ProviderManager, create_provider_manager


def load_provider_manager() -> ProviderManager:
    """Build the provider manager from the configured config file.

    A missing config file yields an empty manager (no providers configured);
    startup must not fail just because the file has not been created yet.
    """
    path = Path(settings.provider_config_file)
    config = ProvidersConfig.from_file(path) if path.exists() else ProvidersConfig(providers={})
    return create_provider_manager(config)


def read_provider_config() -> ProvidersConfig:
    """Load the provider configuration file (an empty config when missing)."""
    path = Path(settings.provider_config_file)
    return ProvidersConfig.from_file(path) if path.exists() else ProvidersConfig(providers={})


def write_provider_config(config: ProvidersConfig) -> None:
    """Atomically persist the provider configuration to the configured file."""
    config.to_file(settings.provider_config_file)


async def reload_provider_manager(request: Request) -> ProviderManager:
    """Rebuild the provider manager from the config file and re-bind services.

    Provider configuration edits (admin scope only) apply immediately: the new
    manager replaces ``app.state.provider_manager``, the chat service starts
    using it, and the RAG service is recreated for the updated set of
    providers. The previous manager/RAG service are closed once the new ones
    are in place.
    """
    from app.services.rag_service import load_rag_service

    manager = load_provider_manager()
    old_manager = getattr(request.app.state, "provider_manager", None)
    request.app.state.provider_manager = manager

    chat_service = getattr(request.app.state, "chat_service", None)
    if chat_service is not None:
        chat_service.provider_manager = manager

    old_rag = getattr(request.app.state, "rag_service", None)
    request.app.state.rag_service = await load_rag_service(manager)
    if old_rag is not None:
        await old_rag.aclose()
    if old_manager is not None:
        await old_manager.aclose()
    return manager


def get_provider_manager(request: Request) -> ProviderManager:
    """FastAPI dependency returning the app's provider manager."""
    return request.app.state.provider_manager


def get_provider_config() -> ProvidersConfig:
    """FastAPI dependency returning the persisted provider configuration.

    Unlike the manager (which only instantiates enabled providers), the config
    also carries disabled providers and credential/model metadata, so
    read-only endpoints can describe the full configured set.
    """
    return read_provider_config()
