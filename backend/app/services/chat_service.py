"""AI chat orchestration.

The chat feature talks to AI **only through the provider interface**
(``ProviderManager`` → ``ChatProvider.chat()/stream()``). No provider SDK and no
direct OpenAI/NVIDIA calls anywhere in this module.

The router's live state (from the dashboard snapshot service) is injected as
read-only context, and the system prompt hard-constrains the model: answer only
from the provided router JSON, never invent router facts.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from ai.core.models import ChatMessage, ChatRequest, ChatResponse
from ai.core.protocols import CAPABILITY_CHAT
from app.services.router_context_cache import RouterContextCache
from app.services.router_diagnosis import RouterDiagnosisEngine
from app.services.router_intent_detector import RouterIntentDetector
from app.services.router_manager import RegisteredRouter, RouterManager, UnknownRouterError
from app.services.router_recommendation import RouterRecommendationEngine
from app.services.router_snapshot import RouterSnapshotService
from app.services.router_tool import RouterTool
from app.services.router_tool_executor import RouterToolExecutor
from app.services.router_tool_registry import RouterToolRegistry
from app.services.router_tool_selector import RouterToolSelector
from providers.base import BaseProvider
from providers.factory import ProviderManager
from router_agent.model import DeviceSnapshot

SYSTEM_PROMPT = (
    "You are the network assistant for an OpenWrt router. You help the user "
    "understand and operate their router.\n\n"
    "The router's CURRENT state is given below as a JSON document. Treat it as "
    "the single source of truth about this router.\n\n"
    "STRICT RULES:\n"
    "1. Answer ONLY from the router state JSON provided. Never invent, guess, "
    "or assume router information that is not present in the JSON (IPs, "
    "hostnames, services, versions, ports, temperatures, tunnel peers, "
    "firewall rules, etc.).\n"
    "2. If router state is absent, or the answer is not derivable from the "
    "JSON, say clearly that you don't have that data for this router. Do not "
    "fabricate values.\n"
    "3. You may explain general networking concepts (e.g. how NAT or WireGuard "
    "works), but clearly label such explanations as general knowledge, not "
    "facts about this specific router.\n"
    "4. You are read-only. You cannot change the router and must never claim "
    "you did.\n"
    "5. Be concise and technically accurate. Use Markdown: short paragraphs, "
    "bullet lists, `inline code` for commands/IPs/MACs, and fenced code blocks "
    "where useful. Do not use emojis."
)


class NoChatProviderError(Exception):
    """Raised when no configured provider supports the chat capability."""


class ChatService:
    """Composes router context and routes chat calls through the provider interface."""

    def __init__(
        self,
        manager: ProviderManager,
        snapshot: Callable[[], DeviceSnapshot | None],
        *,
        router_tool: RouterTool | None = None,
        registry: RouterToolRegistry | None = None,
        selector: RouterToolSelector | None = None,
        detector: RouterIntentDetector | None = None,
        executor: RouterToolExecutor | None = None,
        cache: RouterContextCache | None = None,
        snapshot_service: RouterSnapshotService | None = None,
        router_manager: RouterManager | None = None,
        diagnosis_engine: RouterDiagnosisEngine | None = None,
        recommendation_engine: RouterRecommendationEngine | None = None,
    ) -> None:
        self._manager = manager
        self._snapshot = snapshot
        self._router_tool = router_tool
        self._router_manager = router_manager
        self._diagnosis_engine = (
            diagnosis_engine if diagnosis_engine is not None else RouterDiagnosisEngine()
        )
        self._recommendation_engine = (
            recommendation_engine
            if recommendation_engine is not None
            else RouterRecommendationEngine()
        )
        if router_manager is None:
            if registry is None:
                registry = self._build_registry(router_tool)
            self._registry = registry
            self._selector = selector if selector is not None else RouterToolSelector(registry)
            self._detector = (
                detector if detector is not None else RouterIntentDetector(self._selector)
            )
            self._executor = executor if executor is not None else RouterToolExecutor(registry)
            self._cache = cache if cache is not None else RouterContextCache()
            self._snapshot_service = (
                snapshot_service
                if snapshot_service is not None
                else RouterSnapshotService(self._cache)
            )
        else:
            self._registry = None
            self._selector = None
            self._detector = None
            self._executor = None
            self._cache = None
            self._snapshot_service = None

    @staticmethod
    def _build_registry(router_tool: RouterTool | None) -> RouterToolRegistry:
        return RouterManager.build_registry(router_tool)

    def _resolve_router(self, router_id: str | None) -> RegisteredRouter | None:
        """Resolve the router instance to operate against.

        When a :class:`RouterManager` is configured, the router is resolved by
        its identifier (or the default router when ``router_id`` is ``None``).
        Unknown ids return ``None``. Without a manager, the single configured
        router is returned.
        """
        if self._router_manager is None:
            if self._router_tool is None:
                return None
            return self._router_manager_builtin()
        try:
            if router_id is not None:
                return self._router_manager.resolve(router_id)
            return self._router_manager.default
        except UnknownRouterError:
            return None

    def _router_manager_builtin(self) -> RegisteredRouter:
        """Expose the single configured router as a lightweight registered router."""
        tool = RouterTool(lambda: None) if self._router_tool is None else self._router_tool
        return RegisteredRouter(
            router_id="default",
            tool=tool,
            registry=self._registry,
            selector=self._selector,
            detector=self._detector,
            executor=self._executor,
            cache=self._cache,
            snapshot_service=self._snapshot_service,
        )

    def router_context_markdown(
        self,
        message: str,
        *,
        router_aware: bool | None = None,
        session_id: str | None = None,
        router_id: str | None = None,
    ) -> str | None:
        """Collect router context markdown for ``message``.

        Intent detection is automatic: when the request is not router-related
        the tool layer is skipped entirely. For router requests, the selector
        turns the message into tool requests and the snapshot service combines
        the results (consulting the per-session context cache first) into a
        single immutable snapshot, which is then rendered. When nothing usable
        is produced, this returns ``None`` and the chat proceeds without the
        router section.

        ``router_aware`` overrides detection: ``True`` forces the router layer,
        ``False`` skips it, and ``None`` (default) auto-detects intent.
        ``session_id`` scopes cached results to the conversation.
        ``router_id`` selects the router (default router when ``None``).
        """
        router = self._resolve_router(router_id)
        if router is None:
            return None
        if router_aware is False:
            return None
        if router_aware is None and router.detector.classify(message) == "non-router":
            return None
        requests = router.selector.select(message)
        if not requests:
            return None
        try:
            snapshot = router.snapshot_service.build(router.executor, session_id, requests)
        except Exception:
            return None
        try:
            markdown = router.snapshot_service.render_markdown(snapshot, intents=requests)
            if markdown is None:
                return None
            diagnosis = self._diagnosis_engine.diagnose(snapshot, router_id=router.router_id)
            diagnosis_markdown = diagnosis.render_markdown()
            if diagnosis_markdown is not None:
                markdown = f"{markdown}\n\n{diagnosis_markdown}"
            if diagnosis.findings:
                recommendations = self._recommendation_engine.generate(diagnosis)
                recommendations_markdown = recommendations.render_markdown()
                if recommendations_markdown is not None:
                    markdown = f"{markdown}\n\n{recommendations_markdown}"
            return markdown
        except Exception:
            return None

    def provider_for(self, preferred: str | None = None) -> BaseProvider:
        """Pick a chat-capable provider (never instantiate adapters directly)."""
        provider = self._manager.get_for_capability(CAPABILITY_CHAT, preferred=preferred)
        if provider is None:
            raise NoChatProviderError(
                "No provider with the 'chat' capability is configured. "
                "Add a provider to providers.yaml (e.g. ollama) and restart."
            )
        return provider

    def system_prompt(self) -> str:
        snapshot = self._snapshot()
        if snapshot is None:
            return (
                SYSTEM_PROMPT + "\n\nROUTER STATE: No router state is available — the data "
                "feed is not connected.\n"
                "If the user asks anything about the router, tell them router "
                "data is unavailable and do not invent any values."
            )
        rendered = json.dumps(snapshot.model_dump(mode="json"), indent=2)
        collected = snapshot.meta.collected_at.isoformat()
        return (
            SYSTEM_PROMPT
            + f"\n\nROUTER STATE (collected at {collected}):\n```json\n{rendered}\n```"
        )

    def compose(
        self,
        *,
        message: str,
        history: list[tuple[str, str]],
        model: str | None = None,
        temperature: float | None = None,
        router_context: str | None = None,
    ) -> ChatRequest:
        """Build the full request: system prompt + stored history + user message.

        ``router_context`` (markdown from the router context service) is appended
        to the system prompt when the request is router-aware; when omitted the
        system prompt is unchanged.
        """
        system = self.system_prompt()
        if router_context:
            system = f"{system}\n\nROUTER CONTEXT:\n{router_context}"
        messages = [ChatMessage(role="system", content=system)]
        for role, content in history:
            if role in ("user", "assistant"):
                messages.append(ChatMessage(role=role, content=content))
        messages.append(ChatMessage(role="user", content=message))
        return ChatRequest(
            model=model or "",
            messages=messages,
            temperature=temperature,
        )

    async def complete(
        self,
        provider: BaseProvider,
        request: ChatRequest,
    ) -> ChatResponse:
        """Non-streaming completion through the provider interface."""
        return await provider.chat(request)
