"""Browser session endpoints.

The static operator API keys (``AUTH_ADMIN_API_KEY`` / ``AUTH_READONLY_API_KEY``)
are credentials that must never reach the browser. ``POST /auth/login``
exchanges a key typed by the operator into a short-lived, server-side session
token with exactly the key's scopes. The browser then sends only that session
token. Logout revokes it server-side so a leaked or available token is
immediately worthless; session expiry bounds its lifetime from the start.
"""

from __future__ import annotations

import asyncio
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from app.core.auth import (
    _UNAUTHENTICATED,
    ADMIN_SCOPES,
    READ_SCOPES,
    AuthPrincipal,
    SessionStore,
    _bearer_token,
    require_authentication,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])


class LoginRequest(BaseModel):
    api_key: str = Field(min_length=1, max_length=512)


@router.post("/auth/login", summary="Exchange an operator API key for a browser session")
async def login(request: Request, body: LoginRequest) -> dict:
    """Authenticate an operator API key and mint a scoped browser session.

    Checks the presented key against the configured admin/read-only keys with a
    constant-time comparison (admin takes precedence). Returns a short-lived,
    revocable session token; the master keys are never returned.
    """
    scopes = None
    role = None
    if settings.auth_admin_api_key and hmac.compare_digest(
        settings.auth_admin_api_key, body.api_key
    ):
        scopes, role = ADMIN_SCOPES, "admin"
    elif settings.auth_readonly_api_key and hmac.compare_digest(
        settings.auth_readonly_api_key, body.api_key
    ):
        scopes, role = READ_SCOPES, "readonly"
    if scopes is None:
        await asyncio.sleep(0.3)  # throttle password-style guessing
        raise _UNAUTHENTICATED

    store: SessionStore = request.app.state.auth_sessions
    token, record = store.create(role=role, scopes=scopes)
    return {
        "token": token,
        "role": role,
        "expires_at": record.expires_at.isoformat(),
        "ttl_seconds": store.ttl(),
    }


@router.get("/auth/session", summary="Return the current session identity")
def session_info(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_authentication)],
) -> dict:
    """Return the authenticated identity and, for sessions, its expiry.

    Lets the frontend validate a restored session token without exposing data.
    """
    token = _bearer_token(request.headers)
    store: SessionStore = request.app.state.auth_sessions
    record = store.resolve(token) if token and store is not None else None
    return {
        "role": principal.key_id,
        "token_type": "session" if record else "static",
        "expires_at": record.expires_at.isoformat() if record else None,
    }


@router.post(
    "/auth/logout",
    summary="Revoke the current browser session",
    dependencies=[Depends(require_authentication)],
)
def logout(request: Request) -> dict:
    """Invalidate the presented session server-side.

    Static operator keys cannot be revoked (they are not sessions); the call is
    still harmless and reports success. Every future use of a revoked session
    token is rejected with 401.
    """
    token = _bearer_token(request.headers)
    store: SessionStore = request.app.state.auth_sessions
    if token and store is not None:
        store.revoke(token)
    return {"logged_out": True}
