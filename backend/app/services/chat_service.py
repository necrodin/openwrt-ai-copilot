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
from app.services.router_tool import RouterTool
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
    ) -> None:
        self._manager = manager
        self._snapshot = snapshot
        self._router_tool = router_tool
        if registry is None:
            registry = self._build_registry(router_tool)
        self._registry = registry
        self._selector = selector if selector is not None else RouterToolSelector(registry)

    @staticmethod
    def _build_registry(router_tool: RouterTool | None) -> RouterToolRegistry:
        registry = RouterToolRegistry()
        if router_tool is not None:
            registry.register("system", router_tool.get_system_info)
            registry.register("cpu", router_tool.get_cpu_info)
            registry.register("memory", router_tool.get_memory_info)
            registry.register("storage", router_tool.get_storage_info)
            registry.register("network", router_tool.get_network_info)
        return registry

    def router_context_markdown(self, message: str) -> str | None:
        """Collect router context markdown for ``message`` via the tool selector.

        The selector picks which Router Tool(s) the request needs from the
        registry; when none are required (or the router is unavailable) this
        returns ``None`` and no tool execution happens.
        """
        if self._router_tool is None:
            return None
        intents = self._selector.select(message)
        if not intents:
            return None
        try:
            return self._router_tool.render_markdown(intents=intents)
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
