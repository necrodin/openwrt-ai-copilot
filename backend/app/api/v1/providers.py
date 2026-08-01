"""Provider administration endpoints.

Read-only introspection of configured providers: list, health, capability
detection results, token usage, and served models. Switching providers is done
in the config file; there are deliberately no mutating endpoints here.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.config import settings
from app.services.provider_manager import get_provider_manager
from providers.base import BaseProvider
from providers.factory import ProviderManager

router = APIRouter(tags=["providers"])

Manager = Annotated[ProviderManager, Depends(get_provider_manager)]


def _provider(
    name: str,
    manager: Manager,
) -> BaseProvider:
    try:
        return manager.get_provider(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


Provider = Annotated[BaseProvider, Depends(_provider)]


def _summary(provider: BaseProvider) -> dict:
    return {
        "name": provider.name,
        "type": provider.provider_type,
        "base_url": provider.config.effective_base_url(),
        "static_capabilities": sorted(provider.static_capabilities()),
    }


@router.get("/providers")
def list_providers(
    manager: Manager,
) -> dict:
    providers = [_summary(p) for p in manager.all()]
    return {
        "service": settings.app_name,
        "default_provider": manager.default_name,
        "providers": providers,
    }


@router.get("/providers/{name}")
def provider_detail(
    provider: Provider,
) -> dict:
    return _summary(provider)


@router.get("/providers/{name}/health")
async def provider_health(
    provider: Provider,
) -> dict:
    return {"name": provider.name, "healthy": await provider.health()}


@router.get("/providers/{name}/capabilities")
async def provider_capabilities(
    provider: Provider,
) -> dict:
    caps = await provider.capabilities()
    return {
        "name": provider.name,
        "detected_at": caps.detected_at.isoformat() if caps.detected_at else None,
        "static": caps.static,
        "capabilities": sorted(caps.as_set),
    }


@router.get("/providers/{name}/usage")
def provider_usage(
    provider: Provider,
) -> dict:
    return {"name": provider.name, "usage": provider.token_usage().model_dump()}


@router.get("/providers/{name}/models")
async def provider_models(
    provider: Provider,
) -> dict:
    try:
        models = await provider.list_models()
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean 502
        raise HTTPException(
            status_code=502,
            detail=f"Cannot list models from {provider.name}: {exc}",
        ) from exc
    return {
        "name": provider.name,
        "models": [
            {
                "id": model.id,
                "capabilities": sorted(model.capabilities),
                "context_window": model.context_window,
            }
            for model in models
        ],
    }
