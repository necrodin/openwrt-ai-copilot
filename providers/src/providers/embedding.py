"""Provider-independent embedding platform.

A high-level facade over the provider registry for **single** and **batch**
embedding. It selects an embedding provider, splits oversized batches into
provider-safe chunks, applies a configurable retry policy with exponential
backoff + jitter, enforces per-call timeouts, runs health checks, and reports
aggregated token usage.

Provider selection is **static-first**: the manager's synchronous capability
routing is used when a provider statically declares ``embeddings``; otherwise a
runtime capability probe (the same detection the adapters already expose)
finds providers whose embedding support is discovered from their configured
model or catalog (e.g. Ollama with an ``embed_model``).

Every network operation flows exclusively through the ``EmbeddingProvider``
interface — this module never imports a provider SDK and never talks to
OpenAI/NVIDIA (or any vendor) directly.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Sequence
from dataclasses import dataclass

from ai.core.errors import ProviderError, ProviderUnavailableError, RateLimitError
from ai.core.models import EmbeddingRequest, EmbeddingResponse, EmbeddingVector, TokenUsage, Usage
from ai.core.protocols import CAPABILITY_EMBEDDINGS
from providers.base import BaseProvider
from providers.factory import ProviderManager


class EmbeddingError(ProviderError):
    """Base error for embedding platform operations."""


class NoEmbeddingProviderError(EmbeddingError):
    """Raised when no configured provider supports the embeddings capability."""


#: Failures worth retrying; everything else propagates immediately.
RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    ProviderUnavailableError,
    RateLimitError,
    asyncio.TimeoutError,
)


@dataclass(frozen=True)
class RetryPolicy:
    """Exponential backoff policy used by the embedding factory.

    Embedding calls are idempotent (same input ⇒ same vector), so retrying
    transient failures is always safe. Pass ``RetryPolicy(max_retries=0)`` to
    disable retrying entirely.
    """

    max_retries: int = 3
    base_delay_seconds: float = 0.5
    max_delay_seconds: float = 8.0
    jitter: bool = True

    def delay_for(self, attempt: int) -> float:
        """Backoff delay for ``attempt`` (0-based) with optional jitter."""
        exponent = 2**attempt
        delay = min(self.base_delay_seconds * exponent, self.max_delay_seconds)
        if self.jitter:
            delay *= random.uniform(0.5, 1.0)
        return delay


def chunk_texts(texts: Sequence[str], size: int) -> list[list[str]]:
    """Split a batch into chunks of at most ``size`` items."""
    size = max(1, size)
    return [list(texts[index : index + size]) for index in range(0, len(texts), size)]


class EmbeddingFactory:
    """Single entry point for embedding through the provider interface.

    Args:
        manager: the configured :class:`ProviderManager`.
        retry: retry policy; ``None`` enables the default
            :class:`RetryPolicy` (three retries with backoff).
        default_batch_size: max inputs per embeddings call when the provider
            does not declare ``embed_batch_size``.
        timeout_seconds: per-call timeout enforced with ``asyncio.wait_for``;
            ``None`` defers to the provider transport's configured timeout.
    """

    def __init__(
        self,
        manager: ProviderManager,
        *,
        retry: RetryPolicy | None = None,
        default_batch_size: int = 64,
        timeout_seconds: float | None = None,
    ) -> None:
        self._manager = manager
        self._retry = retry or RetryPolicy()
        self._default_batch_size = max(1, default_batch_size)
        self._timeout_seconds = timeout_seconds

    # ------------------------------------------------------------------ #
    # Introspection                                                      #
    # ------------------------------------------------------------------ #

    def embedding_providers(self) -> list[BaseProvider]:
        """Providers that statically declare the embeddings capability."""
        return [
            provider
            for provider in self._manager.all()
            if CAPABILITY_EMBEDDINGS in provider.static_capabilities()
        ]

    async def _get_provider(self, preferred: str | None) -> BaseProvider:
        """Pick an embedding provider: static routing first, then runtime probe."""
        provider = self._manager.get_for_capability(CAPABILITY_EMBEDDINGS, preferred=preferred)
        if provider is not None:
            return provider
        provider = await self._detect_runtime(preferred)
        if provider is None:
            raise NoEmbeddingProviderError(
                "No provider with the 'embeddings' capability is configured. "
                "Add an embedding-capable provider to providers.yaml and restart."
            )
        return provider

    async def _detect_runtime(self, preferred: str | None) -> BaseProvider | None:
        """Probe configured providers for runtime-detected embedding support."""
        ordered: list[str] = []
        if preferred:
            ordered.append(preferred)
        if self._manager.default_name and self._manager.default_name not in ordered:
            ordered.append(self._manager.default_name)
        ordered.extend(name for name in self._manager.providers if name not in ordered)

        for name in ordered:
            provider = self._manager.providers[name]
            try:
                if await provider.supports(CAPABILITY_EMBEDDINGS):
                    return provider
            except Exception:  # noqa: BLE001 - probe failure just skips provider
                continue
        return None

    async def health(self, *, preferred: str | None = None) -> dict[str, bool]:
        """Health of the embedding-capable providers (never raises)."""
        if preferred is not None:
            provider = await self._get_provider(preferred)
            return {preferred: await provider.health()}
        results: dict[str, bool] = {}
        for name, provider in self._manager.providers.items():
            if CAPABILITY_EMBEDDINGS in provider.static_capabilities():
                try:
                    results[name] = await provider.health()
                except Exception:  # noqa: BLE001 - health must never raise
                    results[name] = False
        return results

    def token_usage(self) -> TokenUsage:
        """Aggregated token usage across all embedding-capable providers."""
        total = TokenUsage()
        for provider in self.embedding_providers():
            total.absorb(provider.token_usage())
        return total

    # ------------------------------------------------------------------ #
    # Public API                                                         #
    # ------------------------------------------------------------------ #

    async def embed(
        self,
        text: str,
        *,
        preferred: str | None = None,
        model: str | None = None,
        input_type: str | None = None,
        normalize: bool = False,
    ) -> list[float]:
        """Embed a single text and return its vector."""
        response = await self.embed_response(
            [text],
            preferred=preferred,
            model=model,
            input_type=input_type,
            normalize=normalize,
        )
        if not response.embeddings:
            raise EmbeddingError("Provider returned no embedding for the text")
        return response.embeddings[0].embedding

    async def embed_batch(
        self,
        texts: Sequence[str],
        *,
        batch_size: int | None = None,
        preferred: str | None = None,
        model: str | None = None,
        input_type: str | None = None,
        normalize: bool = False,
    ) -> list[list[float]]:
        """Embed many texts and return their vectors, batched automatically."""
        response = await self.embed_response(
            texts,
            batch_size=batch_size,
            preferred=preferred,
            model=model,
            input_type=input_type,
            normalize=normalize,
        )
        return [vector.embedding for vector in response.embeddings]

    async def embed_response(
        self,
        texts: Sequence[str],
        *,
        batch_size: int | None = None,
        preferred: str | None = None,
        model: str | None = None,
        input_type: str | None = None,
        normalize: bool = False,
    ) -> EmbeddingResponse:
        """Embed a batch and return the full :class:`EmbeddingResponse`.

        Empty inputs produce an empty response without any provider call.
        """
        texts = list(texts)
        if not texts:
            return EmbeddingResponse(model=model or "", embeddings=[])

        provider = await self._get_provider(preferred)
        resolved_batch = batch_size or provider.config.embed_batch_size or self._default_batch_size

        chunks = chunk_texts(texts, resolved_batch)
        if len(chunks) == 1:
            return await self._call_provider(provider, chunks[0], model, input_type, normalize)

        vectors: list[EmbeddingVector] = []
        prompt_tokens = 0
        completion_tokens = 0
        response_model = model or ""
        for chunk in chunks:
            response = await self._call_provider(provider, chunk, model, input_type, normalize)
            vectors.extend(response.embeddings)
            prompt_tokens += response.usage.prompt_tokens
            completion_tokens += response.usage.completion_tokens
            response_model = response.model or response_model
        return EmbeddingResponse(
            model=response_model,
            embeddings=vectors,
            usage=Usage(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens),
        )

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    async def _call_provider(
        self,
        provider: BaseProvider,
        texts: list[str],
        model: str | None,
        input_type: str | None,
        normalize: bool,
    ) -> EmbeddingResponse:
        request = EmbeddingRequest(
            model=model or "",
            inputs=texts,
            input_type=input_type,
            normalize=normalize,
        )
        attempt = 0
        while True:
            try:
                return await self._execute(provider, request)
            except RETRYABLE_EXCEPTIONS as exc:
                if attempt >= self._retry.max_retries:
                    raise EmbeddingError(
                        f"Embedding failed after {attempt + 1} attempt(s) via "
                        f"{provider.name!r}: {exc}"
                    ) from exc
                await asyncio.sleep(self._retry.delay_for(attempt))
                attempt += 1

    async def _execute(
        self, provider: BaseProvider, request: EmbeddingRequest
    ) -> EmbeddingResponse:
        coroutine = provider.embeddings(request)
        if self._timeout_seconds is not None:
            return await asyncio.wait_for(coroutine, timeout=self._timeout_seconds)
        return await coroutine


__all__ = [
    "EmbeddingError",
    "EmbeddingFactory",
    "NoEmbeddingProviderError",
    "RETRYABLE_EXCEPTIONS",
    "RetryPolicy",
    "chunk_texts",
]
