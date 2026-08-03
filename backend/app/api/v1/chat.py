"""AI chat endpoints.

Everything goes through the provider interface (``ChatProvider``) — never a
provider SDK directly. ``POST /chat`` returns a full reply; ``POST /chat/stream``
streams a Server-Sent Events feed. Both persist the conversation to SQLite.

When RAG chat is enabled (``rag.yaml`` present) the requests are routed through
the :class:`rag.ai.RAGEngine` instead, grounding answers in the retrieval core
and returning citations; the router-state path is untouched otherwise.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.db.chat_store import ChatStore
from app.schemas.chat import ChatRequestBody
from app.services.chat_service import ChatService, NoChatProviderError
from app.services.rag_service import RAGService

router = APIRouter(tags=["chat"])


def _chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


def _router_context_markdown(
    request: Request,
    message: str,
    router_aware: bool | None = None,
) -> str | None:
    """Collect router context markdown for ``message`` via the ChatService.

    Router intent is auto-detected by default; ``router_aware`` only overrides
    detection. Best-effort and never raises so a failing tool never fails the
    chat request.
    """
    try:
        return _chat_service(request).router_context_markdown(message, router_aware=router_aware)
    except Exception:
        return None


def _rag_service(request: Request) -> RAGService | None:
    return getattr(request.app.state, "rag_service", None)


def _sse(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _history_turns(store: ChatStore, session_id: str) -> list[tuple[str, str]]:
    records = store.get_messages(session_id)
    return [(record.role, record.content) for record in records]


def _store_turn(
    store: ChatStore,
    session_id: str,
    role: str,
    content: str,
    *,
    provider: str | None = None,
    model: str | None = None,
) -> None:
    store.add_message(
        session_id=session_id,
        role=role,
        content=content,
        provider=provider,
        model=model,
    )


def _provider_preference(body: ChatRequestBody, rag_service: RAGService | None) -> str | None:
    if body.provider:
        return body.provider
    if rag_service is not None and rag_service.config.provider:
        return rag_service.config.provider
    return None


def _citations_json(citations: list[Any]) -> list[dict]:
    return [citation.model_dump() for citation in citations]


@router.post("/chat")
async def chat(request: Request, body: ChatRequestBody) -> Response:
    """Non-streaming chat. Returns the full assistant reply."""
    service = _chat_service(request)
    store = request.app.state.chat_store
    rag_service = _rag_service(request)
    try:
        provider = service.provider_for(_provider_preference(body, rag_service))
    except NoChatProviderError as exc:
        return Response(
            content=json.dumps({"detail": str(exc)}),
            status_code=503,
            media_type="application/json",
        )

    history = _history_turns(store, body.session_id)
    _store_turn(store, body.session_id, "user", body.message)

    if rag_service is not None:
        rag_service.seed_history(body.session_id, history)
        engine = rag_service.engine_for(body.session_id, provider)
        try:
            response = await engine.answer(
                body.message,
                conversation_id=body.session_id,
                model=body.model,
                temperature=body.temperature,
            )
        except Exception as exc:  # noqa: BLE001 - surfaced as a clean error
            return Response(
                content=json.dumps({"detail": f"AI request failed: {exc}"}),
                status_code=502,
                media_type="application/json",
            )
        _store_turn(
            store,
            body.session_id,
            "assistant",
            response.answer,
            provider=provider.name,
            model=response.model,
        )
        return Response(
            content=json.dumps(
                {
                    "session_id": body.session_id,
                    "reply": response.answer,
                    "provider": provider.name,
                    "model": response.model,
                    "citations": _citations_json(response.citations),
                    "usage": response.usage.model_dump(),
                    "rag": True,
                },
                ensure_ascii=False,
            ),
            status_code=200,
            media_type="application/json",
        )

    chat_request = service.compose(
        message=body.message,
        history=history,
        model=body.model,
        temperature=body.temperature,
        router_context=_router_context_markdown(
            request,
            body.message,
            router_aware=body.router_aware,
        ),
    )
    try:
        response = await service.complete(provider, chat_request)
    except Exception as exc:  # noqa: BLE001 - surfaced as a clean error
        return Response(
            content=json.dumps({"detail": f"AI request failed: {exc}"}),
            status_code=502,
            media_type="application/json",
        )

    content = response.message.content
    reply = content if isinstance(content, str) else json.dumps(content)
    _store_turn(
        store,
        body.session_id,
        "assistant",
        reply,
        provider=provider.name,
        model=response.model,
    )
    return Response(
        content=json.dumps(
            {
                "session_id": body.session_id,
                "reply": reply,
                "provider": provider.name,
                "model": response.model,
                "usage": response.usage.model_dump(),
            },
            ensure_ascii=False,
        ),
        status_code=200,
        media_type="application/json",
    )


@router.post("/chat/stream")
async def chat_stream(request: Request, body: ChatRequestBody) -> StreamingResponse:
    """Streaming chat as Server-Sent Events."""

    async def generator() -> AsyncIterator[str]:
        service = _chat_service(request)
        store = request.app.state.chat_store
        rag_service = _rag_service(request)
        try:
            provider = service.provider_for(_provider_preference(body, rag_service))
        except NoChatProviderError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return

        history = _history_turns(store, body.session_id)
        _store_turn(store, body.session_id, "user", body.message)
        yield _sse({"type": "session", "session_id": body.session_id})

        if rag_service is not None:
            rag_service.seed_history(body.session_id, history)
            engine = rag_service.engine_for(body.session_id, provider)
            reply_parts: list[str] = []
            streamed_model = ""
            try:
                async for event in engine.stream(
                    body.message,
                    conversation_id=body.session_id,
                    model=body.model,
                    temperature=body.temperature,
                ):
                    if event.type == "delta":
                        reply_parts.append(event.content)
                        streamed_model = streamed_model or event.model
                        yield _sse({"type": "delta", "content": event.content})
                    elif event.type == "error":
                        yield _sse({"type": "error", "message": event.error})
                        return
                    elif event.type in ("retrieval", "citations"):
                        yield _sse(
                            {
                                "type": event.type,
                                "citations": _citations_json(event.citations),
                                "usage": event.usage.model_dump(),
                            }
                        )
                    elif event.type in ("session", "generation_started"):
                        yield _sse({"type": event.type, "session_id": body.session_id})
            except Exception as exc:  # noqa: BLE001 - keep streaming contract
                yield _sse({"type": "error", "message": f"AI stream failed: {exc}"})
                return

            reply = "".join(reply_parts)
            _store_turn(
                store,
                body.session_id,
                "assistant",
                reply,
                provider=provider.name,
                model=streamed_model or body.model or provider.config.model or "default",
            )
            yield _sse(
                {
                    "type": "done",
                    "reply": reply,
                    "provider": provider.name,
                    "model": streamed_model or body.model or provider.config.model or "default",
                    "rag": True,
                }
            )
            return

        chat_request = service.compose(
            message=body.message,
            history=history,
            model=body.model,
            temperature=body.temperature,
            router_context=_router_context_markdown(
                request,
                body.message,
                router_aware=body.router_aware,
            ),
        )
        reply_parts = []
        try:
            async for chunk in provider.stream(chat_request):
                if chunk.delta:
                    reply_parts.append(chunk.delta)
                    yield _sse({"type": "delta", "content": chunk.delta})
        except Exception as exc:  # noqa: BLE001 - keep streaming contract
            yield _sse({"type": "error", "message": f"AI stream failed: {exc}"})
            return

        reply = "".join(reply_parts)
        _store_turn(
            store,
            body.session_id,
            "assistant",
            reply,
            provider=provider.name,
            model=body.model or provider.config.model or "default",
        )
        yield _sse(
            {
                "type": "done",
                "reply": reply,
                "provider": provider.name,
                "model": body.model or provider.config.model or "default",
                "usage": None,
            }
        )

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/chat/history")
def chat_history(request: Request, session_id: str = "default") -> dict:
    """Return the stored turns for a session (newest first list order: chronological)."""
    store: ChatStore = request.app.state.chat_store
    records = store.get_messages(session_id)
    return {
        "session_id": session_id,
        "service": settings.app_name,
        "messages": [
            {
                "role": record.role,
                "content": record.content,
                "created_at": record.created_at.isoformat() if record.created_at else None,
                "provider": record.provider,
                "model": record.model,
            }
            for record in records
        ],
    }


@router.get("/chat/sessions")
def chat_sessions(request: Request) -> dict:
    """List known chat sessions, newest first."""
    store: ChatStore = request.app.state.chat_store
    return {"sessions": store.list_sessions()}
