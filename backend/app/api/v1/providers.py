"""Provider administration endpoints.

Two surfaces share one router:

- Read-only introspection (any authenticated reader): list providers, detail,
  health, capability detection, token usage, and served models.
- Provider configuration management (admin/write scope, ``devices.write``):
  add, edit, delete, enable/disable, set default, and test-connection.
  Every mutating endpoint is guarded by ``require_write`` so only the existing
  admin-level authorization (admin API key or an admin browser session) may
  change provider configuration; the read-only key and read-only accounts get
  403. No new role is introduced — configuration edits reuse the current
  provider configuration file (``settings.provider_config_file``), are
  persisted there, and take effect immediately by reloading the provider
  manager.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.auth import AuthPrincipal, require_write
from app.core.config import settings
from app.services.provider_credentials import ProviderCredentialStore
from app.services.provider_diagnostics import discover_provider_models, test_provider_chat
from app.services.provider_manager import (
    get_provider_config,
    get_provider_manager,
    read_provider_config,
    reload_provider_manager,
    write_provider_config,
)
from providers.base import BaseProvider
from providers.config import (
    DEFAULT_BASE_URLS,
    PROVIDER_LABELS,
    SUPPORTED_PROVIDER_TYPES,
    ProviderConfig,
    ProvidersConfig,
)
from providers.factory import ProviderManager

router = APIRouter(tags=["providers"])

Manager = Annotated[ProviderManager, Depends(get_provider_manager)]
Config = Annotated[ProvidersConfig, Depends(get_provider_config)]


class ProviderCreate(BaseModel):
    """Body for ``POST /providers`` (create).

    ``credential`` is the API key itself, write-only: it is encrypted into the
    server-side credential store and never returned or persisted in
    ``providers.yaml``. The legacy ``api_key_env`` (an environment-variable
    name) remains accepted for backward compatibility.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    name: str = ""
    enabled: bool = True
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_ref: str | None = None
    credential: str | None = None
    model: str = ""
    embed_model: str = ""
    vision_model: str = ""
    rerank_model: str = ""
    embed_dimensions: int | None = None
    embed_batch_size: int | None = None
    timeout_seconds: float = 60.0
    verify_tls: bool = True
    extra_headers: dict[str, str] = Field(default_factory=dict)
    capabilities: set[str] | None = None
    cost_per_1k_prompt: float = 0.0
    cost_per_1k_completion: float = 0.0


class ProviderUpdate(BaseModel):
    """Body for ``PATCH /providers/{type}`` (partial edit).

    Only the fields present in the request are applied; omitted fields keep
    their current values. ``capabilities: []`` clears a capability override.

    ``credential`` is write-only: when present and non-empty it *replaces* the
    stored credential; when absent (or empty) the existing credential is kept —
    enforced server-side, never only in the UI. Use
    ``DELETE /providers/{type}/credential`` to remove a stored credential
    explicitly.
    """

    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    enabled: bool | None = None
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_ref: str | None = None
    credential: str | None = None
    model: str | None = None
    embed_model: str | None = None
    vision_model: str | None = None
    rerank_model: str | None = None
    embed_dimensions: int | None = None
    embed_batch_size: int | None = None
    timeout_seconds: float | None = None
    verify_tls: bool | None = None
    extra_headers: dict[str, str] | None = None
    capabilities: set[str] | None = None
    cost_per_1k_prompt: float | None = None
    cost_per_1k_completion: float | None = None


class DefaultRequest(BaseModel):
    """Body for ``POST /providers/default``."""

    model_config = ConfigDict(extra="forbid")

    type: str


class ProviderProbe(BaseModel):
    """Draft configuration used to test/discover a provider before saving.

    Mirrors the common provider fields a user configures in the UI. The
    ``credential`` field carries the (possibly unsaved) API key the operator
    typed in the form; it is used server-side for the test/discovery request and
    never part of any response or stored configuration. The legacy
    ``api_key_env`` name remains accepted.
    """

    model_config = ConfigDict(extra="forbid")

    type: str
    name: str = ""
    base_url: str | None = None
    api_key_env: str | None = None
    api_key_ref: str | None = None
    credential: str | None = None
    model: str = ""
    timeout_seconds: float = 60.0
    verify_tls: bool = True
    extra_headers: dict[str, str] = Field(default_factory=dict)


def _probe_config(body: ProviderProbe) -> ProviderConfig:
    """Validate a draft probe body into a :class:`ProviderConfig`.

    The supplied ``credential`` (unsaved key) is carried in-memory on the
    config's write-only ``api_key`` field so the probe authenticates with
    exactly what the operator typed — without it ever being persisted.
    """
    if body.type not in SUPPORTED_PROVIDER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported provider type {body.type!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_PROVIDER_TYPES))}"
            ),
        )
    data = body.model_dump()
    credential = data.pop("credential", None)
    try:
        cfg = ProviderConfig.model_validate({**data, "type": body.type})
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid provider configuration: {exc.errors()}",
        ) from exc
    if credential:
        cfg.api_key = credential
    return cfg


def _provider(
    name: str,
    manager: Manager,
) -> BaseProvider:
    try:
        return manager.get_provider(name)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


Provider = Annotated[BaseProvider, Depends(_provider)]


def _summary(provider: BaseProvider, *, has_credential: bool) -> dict:
    return {
        "name": provider.name,
        "type": provider.provider_type,
        "base_url": provider.config.effective_base_url(),
        "static_capabilities": sorted(provider.static_capabilities()),
        "has_credential": has_credential,
    }


def _config_summary(
    type_: str,
    cfg: ProviderConfig,
    *,
    default: str | None = None,
    has_credential: bool,
) -> dict:
    """Public description of one configured provider (config-key identity).

    Only safe metadata is exposed: the credential indicator is a boolean; the
    key value (stored encrypted or referenced by ``api_key_env``/``api_key_ref``)
    is never read or returned.
    """
    return {
        "type": type_,
        "name": cfg.effective_name(),
        "enabled": cfg.enabled,
        "is_default": default == type_,
        "has_credential": has_credential,
        "base_url": cfg.effective_base_url(),
        "model": cfg.model,
    }


def _disabled_summary(
    type_: str,
    cfg: ProviderConfig,
    *,
    default: str | None,
    has_credential: bool,
) -> dict:
    """Summary for a provider that is configured but currently disabled.

    Disabled providers are not instantiated by the manager, so there is no
    runtime adapter to probe for static capabilities; the config override set
    (when present) is reported instead.
    """
    return {
        "type": type_,
        "name": cfg.effective_name(),
        "enabled": False,
        "is_default": default == type_,
        "has_credential": has_credential,
        "base_url": cfg.effective_base_url(),
        "model": cfg.model,
        "static_capabilities": sorted(cfg.capabilities or []),
    }


def _validate_provider(type_: str, data: dict) -> ProviderConfig:
    """Validate caller-supplied fields against ``ProviderConfig`` semantics.

    Any write-only ``credential`` carried in ``data`` is applied to the
    config's in-memory ``api_key`` field after validation (it is excluded from
    every serialization, so it can never reach ``providers.yaml``).
    """
    data = {**data, "type": type_}
    credential = data.pop("credential", None)
    try:
        cfg = ProviderConfig.model_validate(data)
    except ValidationError as exc:
        raise HTTPException(
            status_code=422,
            detail=f"Invalid provider configuration: {exc.errors()}",
        ) from exc
    if credential:
        cfg.api_key = credential
    return cfg


def _cfg_has_credential(cfg: ProviderConfig) -> bool:
    """True when a config references a credential (env-var name or ref)."""
    return bool(cfg.api_key_env or cfg.api_key_ref)


def _credential_store(request: Request) -> ProviderCredentialStore:
    """Resolve the application's encrypted provider-credential store."""
    store: ProviderCredentialStore | None = getattr(
        request.app.state, "provider_credentials", None
    )
    if store is None:
        raise HTTPException(
            status_code=503, detail="Provider credential store is not available."
        )
    return store


StoreDep = Annotated[ProviderCredentialStore, Depends(_credential_store)]


@router.get("/providers/types")
def provider_types() -> dict:
    """List the supported provider types a caller can configure (read-only).

    ``label`` is the human-facing name so the UI never hardcodes provider
    names; ``requires_base_url`` flags types whose endpoint must be supplied
    (e.g. the always-available "Custom / OpenAI-compatible" option).
    """
    types = [
        {
            "type": type_,
            "label": PROVIDER_LABELS.get(type_, type_),
            "default_base_url": DEFAULT_BASE_URLS[type_],
            "requires_base_url": not DEFAULT_BASE_URLS[type_],
        }
        for type_ in sorted(SUPPORTED_PROVIDER_TYPES)
    ]
    return {"service": settings.app_name, "types": types}


@router.get("/providers")
def list_providers(
    manager: Manager,
    config: Config,
    store: StoreDep,
) -> dict:
    """List every configured provider (enabled and disabled).

    Enabled providers carry a live summary from the running manager (including
    detected static capabilities); disabled providers are described from the
    configuration file so operators can see and re-enable them. ``enabled``
    and ``is_default`` let the UI render state without probing the network.
    Only a boolean ``has_credential`` is exposed — never the key or the
    environment-variable reference.
    """
    default = manager.default_name
    by_type: dict[str, dict] = {}

    for key, provider in manager.providers.items():
        entry = _summary(provider, has_credential=False)
        entry["enabled"] = True
        entry["is_default"] = default == key
        entry["model"] = ""
        by_type[entry["type"]] = entry

    for type_, cfg in config.providers.items():
        has_credential = _cfg_has_credential(cfg) or store.has(type_)
        if type_ in by_type:
            by_type[type_]["has_credential"] = has_credential
            by_type[type_]["model"] = cfg.model
        elif not cfg.enabled:
            by_type[type_] = _disabled_summary(
                type_, cfg, default=config.default_provider, has_credential=has_credential
            )

    providers = sorted(by_type.values(), key=lambda entry: entry["type"])
    return {
        "service": settings.app_name,
        "default_provider": default,
        "providers": providers,
    }


@router.get("/providers/{name}")
def provider_detail(
    name: str,
    manager: Manager,
    config: Config,
    store: StoreDep,
) -> dict:
    """Return the summary for a single configured provider (incl. disabled)."""
    if name in manager.providers:
        entry = _summary(manager.providers[name], has_credential=False)
        entry["enabled"] = True
        entry["is_default"] = manager.default_name == name
        cfg = config.providers.get(name)
        entry["has_credential"] = bool(
            (cfg and _cfg_has_credential(cfg)) or store.has(name)
        )
        entry["model"] = cfg.model if cfg else ""
        return entry
    cfg = config.providers.get(name)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Provider {name!r} is not configured")
    return _disabled_summary(
        name,
        cfg,
        default=config.default_provider,
        has_credential=_cfg_has_credential(cfg) or store.has(name),
    )


@router.get("/providers/{name}/health")
async def provider_health(
    provider: Provider,
) -> dict:
    """Probe a single provider and report whether it is reachable."""
    return {"name": provider.name, "healthy": await provider.health()}


@router.get("/providers/{name}/capabilities")
async def provider_capabilities(
    provider: Provider,
) -> dict:
    """Return the detected capabilities for a single provider."""
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
    """Return the cumulative token-usage counters for a provider."""
    return {"name": provider.name, "usage": provider.token_usage().model_dump()}


@router.get("/providers/{name}/models")
async def provider_models(
    provider: Provider,
) -> dict:
    """List the models a provider serves (502 when the upstream is unreachable)."""
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


@router.post("/providers", status_code=201)
async def create_provider_route(
    request: Request,
    body: ProviderCreate,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
    store: StoreDep,
) -> dict:
    """Add a new provider (admin/write scope required).

    A supplied ``credential`` is encrypted into the credential store; it never
    appears in ``providers.yaml`` or in the response.
    """
    if body.type not in SUPPORTED_PROVIDER_TYPES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported provider type {body.type!r}; "
                f"supported: {', '.join(sorted(SUPPORTED_PROVIDER_TYPES))}"
            ),
        )
    config = read_provider_config()
    if body.type in config.providers:
        raise HTTPException(
            status_code=409,
            detail=f"Provider {body.type!r} already exists.",
        )
    cfg = _validate_provider(body.type, body.model_dump())
    config.providers[body.type] = cfg
    write_provider_config(config)
    if body.credential:
        store.set(body.type, body.credential)
    await reload_provider_manager(request)
    return _config_summary(
        body.type,
        cfg,
        default=config.default_provider,
        has_credential=_cfg_has_credential(cfg) or store.has(body.type),
    )


@router.patch("/providers/{type}")
async def update_provider_route(
    request: Request,
    type: str,
    body: ProviderUpdate,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
    store: StoreDep,
) -> dict:
    """Edit an existing provider in place (admin/write scope required).

    Credential semantics are enforced server-side: a non-empty ``credential``
    replaces the stored key; an absent/empty ``credential`` keeps it; deletion
    is a separate explicit ``DELETE /providers/{type}/credential`` call.
    """
    config = read_provider_config()
    existing = config.providers.get(type)
    if existing is None:
        raise HTTPException(status_code=404, detail=f"Provider {type!r} is not configured")
    patch = body.model_dump(exclude_unset=True)
    credential = patch.pop("credential", None)
    merged = {**existing.model_dump(), **patch, "type": type}
    cfg = _validate_provider(type, merged)
    config.providers[type] = cfg
    write_provider_config(config)
    if credential is not None and credential.strip():
        store.set(type, credential.strip())
    await reload_provider_manager(request)
    return _config_summary(
        type,
        cfg,
        default=config.default_provider,
        has_credential=_cfg_has_credential(cfg) or store.has(type),
    )


@router.delete("/providers/{type}")
async def delete_provider_route(
    request: Request,
    type: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
    store: StoreDep,
) -> dict:
    """Remove a provider and its stored credential (admin/write scope required)."""
    config = read_provider_config()
    if type not in config.providers:
        raise HTTPException(status_code=404, detail=f"Provider {type!r} is not configured")
    del config.providers[type]
    if config.default_provider == type:
        config.default_provider = None
    write_provider_config(config)
    store.remove(type)
    await reload_provider_manager(request)
    return {"deleted": True, "type": type}


@router.delete("/providers/{type}/credential")
async def remove_provider_credential_route(
    type: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
    store: StoreDep,
) -> dict:
    """Remove a provider's stored credential without deleting the provider.

    Explicit removal only — an empty credential on PATCH keeps the existing key.
    """
    config = read_provider_config()
    if type not in config.providers:
        raise HTTPException(status_code=404, detail=f"Provider {type!r} is not configured")
    removed = store.remove(type)
    return {
        "type": type,
        "has_credential": _cfg_has_credential(config.providers[type]) or store.has(type),
        "removed": removed,
    }


@router.post("/providers/{type}/enable")
async def enable_provider_route(
    request: Request,
    type: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
    store: StoreDep,
) -> dict:
    """Enable a provider (admin/write scope required)."""
    config = read_provider_config()
    cfg = config.providers.get(type)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Provider {type!r} is not configured")
    if not cfg.enabled:
        cfg.enabled = True
        write_provider_config(config)
        await reload_provider_manager(request)
    return _config_summary(
        type,
        cfg,
        default=config.default_provider,
        has_credential=_cfg_has_credential(cfg) or store.has(type),
    )


@router.post("/providers/{type}/disable")
async def disable_provider_route(
    request: Request,
    type: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
    store: StoreDep,
) -> dict:
    """Disable a provider without removing its configuration (admin/write scope).

    The stored credential is preserved across enable/disable cycles.
    """
    config = read_provider_config()
    cfg = config.providers.get(type)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Provider {type!r} is not configured")
    if cfg.enabled:
        cfg.enabled = False
        write_provider_config(config)
        await reload_provider_manager(request)
    return _config_summary(
        type,
        cfg,
        default=config.default_provider,
        has_credential=_cfg_has_credential(cfg) or store.has(type),
    )


@router.post("/providers/default")
async def set_default_provider_route(
    request: Request,
    body: DefaultRequest,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Set the default provider for unqualified AI calls (admin/write scope)."""
    config = read_provider_config()
    cfg = config.providers.get(body.type)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Provider {body.type!r} is not configured")
    if not cfg.enabled:
        raise HTTPException(
            status_code=400,
            detail=f"Cannot set disabled provider {body.type!r} as the default",
        )
    if config.default_provider != body.type:
        config.default_provider = body.type
        write_provider_config(config)
        await reload_provider_manager(request)
    return {"default_provider": body.type}


@router.post("/providers/test")
async def test_draft_provider_route(
    body: ProviderProbe,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Test a *draft* provider configuration before it is saved.

    Runs a real chat completion with the configured model against the supplied
    base URL/credential env-var name and returns a categorized result
    (``ok``/``endpoint_unreachable``/``authentication_failed``/
    ``model_not_found``/``rate_limited``/``provider_rejected``/``timeout``/
    ``invalid_configuration``). The credential value is never transmitted: only
    its environment-variable name is accepted and resolved server-side.
    """
    return await test_provider_chat(_probe_config(body))


@router.post("/providers/discover-models")
async def discover_provider_models_route(
    body: ProviderProbe,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """List the models served by a draft provider configuration.

    Lets the UI populate a model dropdown from the endpoint's ``/models`` list
    (manual entry remains available when listing is unsupported or fails).
    """
    return await discover_provider_models(_probe_config(body))


@router.post("/providers/{type}/test")
async def test_provider_connection_route(
    type: str,
    principal: Annotated[AuthPrincipal, Depends(require_write)],
) -> dict:
    """Test a saved provider without changing configuration.

    Unlike a reachability probe, this verifies the configured model can answer
    a real chat request. Works for enabled and disabled providers alike: a
    temporary provider is built from the stored configuration and closed
    afterwards.
    """
    config = read_provider_config()
    cfg = config.providers.get(type)
    if cfg is None:
        raise HTTPException(status_code=404, detail=f"Provider {type!r} is not configured")
    return await test_provider_chat(cfg)
