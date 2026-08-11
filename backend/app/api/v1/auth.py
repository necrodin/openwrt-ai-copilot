"""Browser session endpoints.

Browser users authenticate with a username and password configured server-side
(``AUTH_ADMIN_USERNAME``/``AUTH_ADMIN_PASSWORD`` for full access,
``AUTH_READONLY_USERNAME``/``AUTH_READONLY_PASSWORD`` for read-only). The
credentials are operator secrets that must never reach the browser. ``POST
/auth/login`` exchanges a username/password for a short-lived, server-side
session token with exactly the role's scopes. The browser then sends only that
session token. Logout revokes it server-side so a leaked or available token is
immediately worthless; session expiry bounds its lifetime from the start.

Programmatic clients never use this endpoint: they authenticate as before with
``Authorization: Bearer <AUTH_*_API_KEY>``.
"""

from __future__ import annotations

import asyncio
import hmac
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from app.core.auth import (
    ADMIN_SCOPES,
    READ_SCOPES,
    AuthPrincipal,
    SessionStore,
    _bearer_token,
    require_authentication,
)
from app.core.config import settings

router = APIRouter(tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid username or password.",
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=512)


def _constant_time_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


@router.post("/auth/login", summary="Sign in with an admin or read-only username")
async def login(request: Request, body: LoginRequest) -> dict:
    """Authenticate a browser user and mint a scoped session.

    Compares the presented username/password against the configured admin and
    read-only accounts with constant-time comparisons (admin takes precedence).
    Returns a short-lived, revocable session token; credentials are never
    returned. Unknown or mismatched credentials are rejected without revealing
    which field was wrong.
    """
    scopes = None
    role = None
    if (
        settings.auth_admin_username
        and settings.auth_admin_password
        and _constant_time_equal(settings.auth_admin_username, body.username)
        and _constant_time_equal(settings.auth_admin_password, body.password)
    ):
        scopes, role = ADMIN_SCOPES, "admin"
    elif (
        settings.auth_readonly_username
        and settings.auth_readonly_password
        and _constant_time_equal(settings.auth_readonly_username, body.username)
        and _constant_time_equal(settings.auth_readonly_password, body.password)
    ):
        scopes, role = READ_SCOPES, "readonly"

    if scopes is None:
        await asyncio.sleep(0.3)  # throttle password-style guessing
        raise _INVALID_CREDENTIALS

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
