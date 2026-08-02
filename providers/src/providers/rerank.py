"""Provider-independent reranking platform.

A high-level facade over the provider registry for **single** reranking calls.
It selects a reranker provider (static capability routing first, runtime probe
as a fallback), applies the same exponential-backoff retry policy used by the
embedding factory, enforces per-call timeouts, and reports aggregated token
usage.

Provider selection mirrors :class:`providers.embedding.EmbeddingFactory`:
the manager's synchronous capability routing is used when a provider statically
declares ``rerank``; otherwise configured providers are probed at runtime (the
same detection the adapters already expose).

Every network operation flows exclusively through the ``RerankerProvider``
interface — this module never imports a provider SDK and never talks to a
vendor directly.
"""

from __future__ import annotations

import asyncio
from collections.abc import Sequence

from ai.core.errors import ProviderError
from ai.core.models import RerankRequest, RerankResponse, TokenUsage
from ai.core.protocols import CAPABILITY_RERANK
from providers.base import BaseProvider
from providers.embedding import RETRYABLE_EXCEPTIONS, RetryPolicy
from providers.factory import ProviderManager


class RerankError(ProviderError):
    """Base error for reranking platform operations."""


class NoRerankProviderError(RerankError):
    """Raised when no configured provider supports the rerank capability."""


class RerankFactory:
    """Single entry point for reranking through the provider interface.

    Args:
        manager: the configured :class:`ProviderManager`.
        retry: retry policy; ``None`` enables the default
            :class:`RetryPolicy` (three retries with backoff).
        timeout_seconds: per-call timeout enforced with ``asyncio.wait_for``;
            ``None`` defers to the provider transport's configured timeout.
    """

    def __init__(
        self,
        manager: ProviderManager,
        *,
        retry: RetryPolicy | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self._manager = manager
        self._retry = retry or RetryPolicy()
        self._timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #

    def rerank_providers(self) -> list[BaseProvider]:
        """Providers that statically declare the rerank capability."""
        return [
            provider
            for provider in self._manager.all()
            if CAPABILITY_RERANK in provider.static_capabilities()
        ]

    async def _get_provider(self, preferred: str | None) -> BaseProvider:
        """Pick a reranker provider: static routing first, then runtime probe."""
        provider = self._manager.get_for_capability(CAPABILITY_RERANK, preferred=preferred)
        if provider is not None:
            return provider
        provider = await self._detect_runtime(preferred)
        if provider is None:
            raise NoRerankProviderError(
                "No provider with the 'rerank' capability is configured. "
                "Add a rerank-capable provider (e.g. nim) to providers.yaml and restart."
            )
        return provider

    async def _detect_runtime(self, preferred: str | None) -> BaseProvider | None:
        """Probe configured providers for runtime-detected rerank support."""
        ordered: list[str] = []
        if preferred:
            ordered.append(preferred)
        if self._manager.default_name and self._manager.default_name not in ordered:
            ordered.append(self._manager.default_name)
        ordered.extend(name for name in self._manager.providers if name not in ordered)

        for name in ordered:
            provider = self._manager.providers[name]
            try:
                if await provider.supports(CAPABILITY_RERANK):
                    return provider
            except Exception:  # noqa: BLE001 - probe failure just skips provider
                continue
        return None

    async def health(self, *, preferred: str | None = None) -> dict[str, bool]:
        """Health of the rerank-capable providers (never raises)."""
        if preferred is not None:
            provider = await self._get_provider(preferred)
            return {preferred: await provider.health()}
        results: dict[str, bool] = {}
        for name, provider in self._manager.providers.items():
            if CAPABILITY_RERANK in provider.static_capabilities():
                try:
                    results[name] = await provider.health()
                except Exception:  # noqa: BLE001 - health must never raise
                    results[name] = False
        return results

    def token_usage(self) -> TokenUsage:
        """Aggregated token usage across all rerank-capable providers."""
        total = TokenUsage()
        for provider in self.rerank_providers():
            total.absorb(provider.token_usage())
        return total

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def rerank(
        self,
        query: str,
        documents: Sequence[str],
        *,
        top_n: int | None = None,
        preferred: str | None = None,
        model: str | None = None,
    ) -> RerankResponse:
        """Score ``documents`` against ``query`` and return the top-N results.

        Empty inputs produce an empty response without any provider call.
        """
        documents = list(documents)
        if not documents:
            return RerankResponse(model=model or "", results=[])

        provider = await self._get_provider(preferred)
        request = RerankRequest(
            model=model or "",
            query=query,
            documents=documents,
            top_n=top_n,
        )
        attempt = 0
        while True:
            try:
                coroutine = provider.rerank(request)
                if self._timeout_seconds is not None:
                    return await asyncio.wait_for(coroutine, timeout=self._timeout_seconds)
                return await coroutine
            except RETRYABLE_EXCEPTIONS as exc:
                if attempt >= self._retry.max_retries:
                    raise RerankError(
                        f"Rerank failed after {attempt + 1} attempt(s) via {provider.name!r}: {exc}"
                    ) from exc
                await asyncio.sleep(self._retry.delay_for(attempt))
                attempt += 1


__all__ = ["NoRerankProviderError", "RerankError", "RerankFactory"]
