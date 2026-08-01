"""AI chat endpoints.

Everything goes through the provider interface (``ChatProvider``) — never a
provider SDK directly. ``POST /chat`` returns a full reply; ``POST /chat/stream``
streams a Server-Sent Events feed. Both persist the conversation to SQLite.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator

from fastapi import APIRouter, Request, Response
from fastapi.responses import StreamingResponse

from app.core.config import settings
from app.db.chat_store import ChatStore
from app.schemas.chat import ChatRequestBody
from app.services.chat_service import ChatService, NoChatProviderError

router = APIRouter(tags=["chat"])


def _chat_service(request: Request) -> ChatService:
    return request.app.state.chat_service


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


@router.post("/chat")
async def chat(request: Request, body: ChatRequestBody) -> Response:
    """Non-streaming chat. Returns the full assistant reply."""
    service = _chat_service(request)
    store = request.app.state.chat_store
    try:
        provider = service.provider_for(body.provider)
    except NoChatProviderError as exc:
        return Response(
            content=json.dumps({"detail": str(exc)}),
            status_code=503,
            media_type="application/json",
        )

    history = _history_turns(store, body.session_id)
    chat_request = service.compose(
        message=body.message,
        history=history,
        model=body.model,
        temperature=body.temperature,
    )
    _store_turn(store, body.session_id, "user", body.message)
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
        try:
            provider = service.provider_for(body.provider)
        except NoChatProviderError as exc:
            yield _sse({"type": "error", "message": str(exc)})
            return

        history = _history_turns(store, body.session_id)
        chat_request = service.compose(
            message=body.message,
            history=history,
            model=body.model,
            temperature=body.temperature,
        )
        _store_turn(store, body.session_id, "user", body.message)
        yield _sse({"type": "session", "session_id": body.session_id})

        reply_parts: list[str] = []
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
