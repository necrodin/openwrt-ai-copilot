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


def get_provider_manager(request: Request) -> ProviderManager:
    """FastAPI dependency returning the app's provider manager."""
    return request.app.state.provider_manager
