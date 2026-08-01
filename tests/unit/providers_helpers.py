"""Helpers for provider adapter tests (MockTransport, no network)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx

from providers.config import ProviderConfig
from providers.transport import ProviderTransport


def make_mock_client(
    handler: Callable[[httpx.Request], httpx.Response],
) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def make_provider(
    provider_cls: type,
    handler: Callable[[httpx.Request], httpx.Response],
    **config_kwargs: Any,
):
    """Build a provider backed by a mock HTTP transport."""
    if "type" not in config_kwargs:
        config_kwargs["type"] = provider_cls.provider_type
    config = ProviderConfig(**config_kwargs)
    client = make_mock_client(handler)
    transport = ProviderTransport(base_url=config.effective_base_url(), client=client)
    return provider_cls(config, transport=transport)
