"""E2E every-test evals: LLM provider specs and adapters (Pydantic + httpx).

Each configured LLM/provider gets an adapter so the every-test harness can run
against a real model endpoint without importing an SDK:

* :class:`OpenAIDeepSeekAdapter` — OpenAI-compatible wire (DeepSeek public API).
  This is the live provider the harness uses by default.
* :class:`AnthropicQwenCloudAdapter` — Anthropic Messages wire for the Aliyun
  QwenCloud token-plan endpoint (used when a valid key + base URL are set).
* :class:`OllamaAdapter` — local Ollama; guarded: the known-broken 4096-token
  profile is refused with a clear error rather than silently used.

Token accounting and budgets are typed (:class:`TokenCount`, :class:`Budget`,
:class:`EstimatedTokens`, :class:`LlmUsageRecord`);
:class:`LlmResult` holds the reply plus its account data.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx
from pydantic import BaseModel, Field

from e2e_evals.domains import MIN_REQUIRED_CONTEXT_TOKENS

# --------------------------------------------------------------------------- #
# Token accounting                                                            #
# --------------------------------------------------------------------------- #


class TokenCount(BaseModel):
    """Structured token accounting for one request."""

    prompt_tokens: int = 0
    completion_tokens: int = 0

    @property
    def total(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class EstimatedTokens(BaseModel):
    """Deterministic token estimate (chars / 3.5, ~word-based heuristic)."""

    chars: int = 0
    estimated_tokens: int = 0

    @classmethod
    def of(cls, text: str) -> EstimatedTokens:
        return cls(chars=len(text), estimated_tokens=round(len(text) / 3.5))


class Budget(BaseModel):
    """Token budget a run can spend; enforces the context floor."""

    max_input_tokens: int = MIN_REQUIRED_CONTEXT_TOKENS
    used_input_tokens: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.max_input_tokens - self.used_input_tokens)

    def within_floor(self) -> bool:
        """True when the required context comfortably fits the budget."""
        return self.max_input_tokens >= 4 * self.used_input_tokens


class LlmUsageRecord(BaseModel):
    """One LLM round-trip record for a question."""

    provider: str = ""
    model: str = ""
    question: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    prompt_chars: int = 0
    reply_chars: int = 0


class LlmResult(BaseModel):
    """The outcome of a real LLM call."""

    reply: str = ""
    text: str = ""
    usage: TokenCount = Field(default_factory=TokenCount)
    latency_ms: int = 0
    ok: bool = False
    error: str | None = None


class LlmProviderSpec(BaseModel):
    """Declarative description of a configurable LLM endpoint."""

    provider: str
    model: str
    wire: str = "openai"  # openai | anthropic | ollama
    base_url: str = ""
    context_window: int = MIN_REQUIRED_CONTEXT_TOKENS
    production_capable: bool = True
    broken_path_reason: str = ""


# --------------------------------------------------------------------------- #
# Adapter protocol                                                            #
# --------------------------------------------------------------------------- #


class LlmAdapter(ABC):
    """Abstraction over a real LLM endpoint (no SDK, plain HTTP)."""

    def __init__(self, provider: str, model: str) -> None:
        self.provider = provider
        self.model = model

    @property
    @abstractmethod
    def wire(self) -> str:
        """Wire format used by this adapter (``openai``/``anthropic``/``ollama``)."""

    @abstractmethod
    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int,
    ) -> LlmResult:
        """Send ``messages`` (role/content dicts) and return the result."""

    @abstractmethod
    async def aclose(self) -> None:
        """Release any held HTTP client."""


# --------------------------------------------------------------------------- #
# OpenAI-compatible wire (DeepSeek, generic)                                  #
# --------------------------------------------------------------------------- #


class OpenAIDeepSeekAdapter(LlmAdapter):
    """Real DeepSeek API over the OpenAI-compatible wire."""

    wire = "openai"
    base = "https://api.deepseek.com"

    def __init__(
        self,
        *,
        model: str = "deepseek-chat",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        super().__init__("deepseek", model)
        if not api_key:
            raise ValueError("DEEPSEEK_API_KEY is required for the DeepSeek adapter")
        self._client = httpx.AsyncClient(
            base_url=base_url or self.base,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 1024,
    ) -> LlmResult:
        started = time.monotonic()
        payload = {"model": self.model, "messages": messages, "max_tokens": max_tokens}
        try:
            response = await self._client.post("/chat/completions", json=payload)
            response.raise_for_status()
            data = response.json()
            usage = data.get("usage") or {}
            reply = (data.get("choices") or [{}])[0].get("message", {}).get("content") or ""
            return LlmResult(
                reply=reply,
                text=reply,
                usage=TokenCount(
                    prompt_tokens=int(usage.get("prompt_tokens") or 0),
                    completion_tokens=int(usage.get("completion_tokens") or 0),
                ),
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=True,
            )
        except httpx.HTTPStatusError as exc:
            return LlmResult(
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=False,
                error=f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            )
        except httpx.HTTPError as exc:
            return LlmResult(
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=False,
                error=str(exc),
            )

    async def aclose(self) -> None:
        await self._client.aclose()


# --------------------------------------------------------------------------- #
# Anthropic Messages wire (Aliyun QwenCloud token-plan)                       #
# --------------------------------------------------------------------------- #


class AnthropicQwenCloudAdapter(LlmAdapter):
    """QwenCloud via the Anthropic Messages API wire format.

    Used when ``ALIYUN_QWENCLOUD_API_KEY`` and ``ALIYUN_QWENCLOUD_BASE_URL``
    are set; the default endpoint is the token-plan ``/apps/anthropic/v1``.
    """

    wire = "anthropic"
    base = "https://token-plan.ap-southeast-1.maas.aliyuncs.com/apps/anthropic/v1"

    def __init__(
        self,
        *,
        model: str = "qwen3.6-flash",
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 120.0,
    ) -> None:
        super().__init__("qwencloud", model)
        if not api_key:
            raise ValueError("ALIYUN_QWENCLOUD_API_KEY is required for the QwenCloud adapter")
        self._client = httpx.AsyncClient(
            base_url=base_url or self.base,
            headers={
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01",
                "content-type": "application/json",
            },
            timeout=timeout,
        )

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 1024,
    ) -> LlmResult:
        system = "\n\n".join(m["content"] for m in messages if m.get("role") == "system")
        user_msgs = [m for m in messages if m.get("role") != "system"]
        if not user_msgs:
            user_msgs = [{"role": "user", "content": messages[-1].get("content", "")}]
        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "messages": user_msgs,
        }
        if system:
            payload["system"] = system
        started = time.monotonic()
        try:
            response = await self._client.post("/messages", json=payload)
            response.raise_for_status()
            data = response.json()
            blocks = data.get("content") or []
            reply = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            usage = data.get("usage") or {}
            return LlmResult(
                reply=reply,
                text=reply,
                usage=TokenCount(
                    prompt_tokens=int(usage.get("input_tokens") or 0),
                    completion_tokens=int(usage.get("output_tokens") or 0),
                ),
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=True,
            )
        except httpx.HTTPStatusError as exc:
            return LlmResult(
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=False,
                error=f"HTTP {exc.response.status_code}: {exc.response.text[:500]}",
            )
        except httpx.HTTPError as exc:
            return LlmResult(
                latency_ms=int((time.monotonic() - started) * 1000),
                ok=False,
                error=str(exc),
            )

    async def aclose(self) -> None:
        await self._client.aclose()


# --------------------------------------------------------------------------- #
# Local Ollama (guarded)                                                      #
# --------------------------------------------------------------------------- #


class OllamaAdapter(LlmAdapter):
    """Local Ollama endpoint — intentionally guarded.

    The 4096-token profile (``qwen2.5-coder:14b``) is a known broken path for
    router-context chat; :meth:`generate` refuses it with :class:`BrokenContextError`
    instead of silently running with an undersized context window.
    """

    wire = "ollama"
    base = "http://127.0.0.1:11434"

    def __init__(
        self,
        *,
        model: str,
        base_url: str | None = None,
        timeout: float = 120.0,
        context_window: int = MIN_REQUIRED_CONTEXT_TOKENS,
    ) -> None:
        super().__init__("ollama", model)
        self._client = httpx.AsyncClient(base_url=base_url or self.base, timeout=timeout)
        self.context_window = context_window

    async def generate(
        self,
        messages: list[dict[str, Any]],
        *,
        max_tokens: int = 1024,
    ) -> LlmResult:
        raise BrokenContextError(
            f"refusing {self.model}: {self.context_window}-token context is below the "
            f"{MIN_REQUIRED_CONTEXT_TOKENS}-token floor required by the every-test "
            "harness (known-broken local Ollama path)"
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class BrokenContextError(RuntimeError):
    """Raised when a configured model cannot hold the required context."""


# --------------------------------------------------------------------------- #
# Factory                                                                     #
# --------------------------------------------------------------------------- #


def make_adapter(
    provider: str,
    model: str,
    *,
    api_key: str | None = None,
    base_url: str | None = None,
) -> LlmAdapter:
    """Build the adapter for ``provider`` (``deepseek`` default, ``qwencloud``,
    or ``ollama``). Raises when the provider is unknown or unconfigured."""
    if provider == "deepseek":
        return OpenAIDeepSeekAdapter(model=model, api_key=api_key, base_url=base_url)
    if provider == "qwencloud":
        return AnthropicQwenCloudAdapter(model=model, api_key=api_key, base_url=base_url)
    if provider == "ollama":
        return OllamaAdapter(model=model, base_url=base_url)
    raise ValueError(f"unknown every-test LLM provider: {provider!r}")


__all__ = [
    "AnthropicQwenCloudAdapter",
    "BrokenContextError",
    "Budget",
    "EstimatedTokens",
    "LlmAdapter",
    "LlmProviderSpec",
    "LlmResult",
    "LlmUsageRecord",
    "OllamaAdapter",
    "OpenAIDeepSeekAdapter",
    "TokenCount",
    "make_adapter",
]