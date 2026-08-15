"""Provider connection diagnostics.

A connection is only considered healthy when the *exact configured model* can
actually answer a chat request — not merely when the endpoint is reachable.
Both probes build a temporary provider from a configuration (never touching the
running manager) and close it afterwards:

- :func:`test_provider_chat` — sends a tiny **streaming** completion
  (``"Reply only: OK"``) through the real chat/completions path and
  categorizes any failure. Streaming is deliberate: the Copilot's live chat
  uses ``POST /chat/stream`` (``provider.stream``), so a test that verified
  only the non-streaming path could report "Connection OK" while the very next
  streaming request failed. The probe exercises the same transport,
  credential, model, and ``stream`` flag the Copilot sends — so "Connection
  OK" genuinely means a real streaming reply works.
- :func:`discover_provider_models` — lists the models the endpoint serves so
  the UI can populate a model dropdown (falls back to manual entry).

Failure categories are intentionally small and stable (mirrored by the
frontend): ``endpoint_unreachable``, ``authentication_failed``,
``model_not_found``, ``rate_limited``, ``provider_rejected``, ``timeout``,
``invalid_configuration``. Credentials are never part of any result — probes
resolve the API key server-side from the configured environment-variable name
and only ever return status/message/model data.
"""

from __future__ import annotations

import time
from typing import Any

from pydantic import ValidationError

from ai.core.errors import (
    AuthenticationError,
    ProviderError,
    ProviderUnavailableError,
    RateLimitError,
)
from ai.core.models import ChatMessage, ChatRequest, ModelInfo
from providers.config import ProviderConfig
from providers.factory import create_provider

#: Tiny completion used to prove the chat/completions path works. Never an
#: expensive evaluation.
TEST_PROMPT = "Reply only: OK"
TEST_MAX_TOKENS = 32

_INVALID_BUILD = {
    "ok": False,
    "category": "invalid_configuration",
    "message": "Could not build the provider.",
}

_MODEL_NOT_FOUND_MARKERS = (
    "does not exist",
    "doesn't exist",
    "not found",
    "model_not_found",
    "unknown model",
    "no such model",
    "unknown model id",
)


def categorize_failure(exc: Exception) -> tuple[str, str]:
    """Map an exception from a provider probe to ``(category, message)``."""
    message = str(exc)
    lowered = message.lower()

    if isinstance(exc, AuthenticationError):
        return "authentication_failed", message
    if isinstance(exc, RateLimitError):
        return "rate_limited", message
    if isinstance(exc, (KeyError, ValueError, ValidationError)):
        return "invalid_configuration", message
    if isinstance(exc, ProviderUnavailableError):
        if "timeout" in lowered or "timed out" in lowered:
            return "timeout", message
        if any(marker in lowered for marker in _MODEL_NOT_FOUND_MARKERS):
            return "model_not_found", message
        return "endpoint_unreachable", message
    if isinstance(exc, ProviderError):
        if any(marker in lowered for marker in _MODEL_NOT_FOUND_MARKERS):
            return "model_not_found", message
        return "provider_rejected", message
    return "invalid_configuration", message


def _probe_result(
    exc: Exception,
) -> dict[str, Any]:
    category, message = categorize_failure(exc)
    return {"ok": False, "category": category, "message": message}


def _build(cfg: ProviderConfig):
    """Instantiate a temporary provider from a config or None on failure."""
    try:
        return create_provider(cfg), None
    except Exception as exc:  # noqa: BLE001 - categorized below
        return None, _probe_result(exc)


async def test_provider_chat(cfg: ProviderConfig) -> dict[str, Any]:
    """Run a minimal *streaming* chat completion with the configured model.

    Streams with the exact contract the Copilot uses (same provider adapter,
    transport, credential resolution, model, and ``stream`` flag) so a
    ``ok: true`` result guarantees the live ``/chat/stream`` path can produce a
    real reply — not merely that a non-streaming completion works. Returns
    ``ok: true`` with the model/reply/latency only when the endpoint is
    reachable, authentication is accepted, the model is valid, and a minimal
    streaming completion succeeds.
    """
    if not cfg.model:
        return {
            "ok": False,
            "category": "invalid_configuration",
            "message": "No model is configured. Set a model before testing.",
        }

    provider, error = _build(cfg)
    if provider is None:
        return error or _INVALID_BUILD

    request = ChatRequest(
        model=cfg.model,
        messages=[ChatMessage(role="user", content=TEST_PROMPT)],
        max_tokens=TEST_MAX_TOKENS,
    )
    started = time.monotonic()
    parts: list[str] = []
    streamed_model = ""
    try:
        async for chunk in provider.stream(request):
            if chunk.delta:
                parts.append(chunk.delta)
            if chunk.model:
                streamed_model = chunk.model
    except Exception as exc:  # noqa: BLE001 - categorized for the caller
        return _probe_result(exc)
    finally:
        await provider.aclose()

    latency_ms = round((time.monotonic() - started) * 1000)
    return {
        "ok": True,
        "category": "ok",
        "message": "Connection OK — the configured model streamed a test reply.",
        "model": streamed_model or cfg.model,
        "reply": "".join(parts)[:200],
        "latency_ms": latency_ms,
    }


async def discover_provider_models(cfg: ProviderConfig) -> dict[str, Any]:
    """List the models an endpoint serves, or a categorized failure.

    Works against a draft configuration (type + base URL + credential env var)
    so the UI can populate a model dropdown before the provider is saved. When
    listing is unavailable the caller keeps manual model entry.
    """
    provider, error = _build(cfg)
    if provider is None:
        return error or _INVALID_BUILD

    try:
        models: list[ModelInfo] = await provider.list_models()
    except Exception as exc:  # noqa: BLE001 - categorized for the caller
        return _probe_result(exc)
    finally:
        await provider.aclose()

    return {
        "ok": True,
        "models": [
            {
                "id": model.id,
                "capabilities": sorted(model.capabilities),
                "context_window": model.context_window,
            }
            for model in models
        ],
    }


__all__ = [
    "TEST_MAX_TOKENS",
    "TEST_PROMPT",
    "categorize_failure",
    "discover_provider_models",
    "test_provider_chat",
]
