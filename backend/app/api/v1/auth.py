"""Browser session endpoints.

Browser users authenticate against stored application-user accounts (see the
first-run setup flow in ``app.api.v1.setup``): ``POST /auth/login`` exchanges a
username/password for a short-lived, server-side session token with exactly the
account's role scopes. Passwords are validated with bcrypt; only the hash is
stored. The browser then sends only that session token. Logout revokes it
server-side so a leaked or available token is immediately worthless.

Programmatic clients never use this endpoint: they authenticate as before with
``Authorization: Bearer <AUTH_*_API_KEY>``.
"""

from __future__ import annotations

import asyncio
from functools import lru_cache
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
from app.core.passwords import hash_password, normalize_username, verify_password
from app.db.user_store import UserStore
from app.db.user_store import store as default_user_store

router = APIRouter(tags=["auth"])

_INVALID_CREDENTIALS = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Invalid username or password.",
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=256)
    password: str = Field(min_length=1, max_length=512)


def _user_store(request: Request) -> UserStore:
    """Resolve the user store (isolated stores can replace the default)."""
    return getattr(request.app.state, "user_store", None) or default_user_store


@lru_cache(maxsize=1)
def _timing_dummy_hash() -> str:
    """A valid bcrypt hash so a failed login costs a bcrypt verify too.

    Equalizes the timing difference between "unknown username" and "wrong
    password" so neither the username space nor the password space is probed
    faster, and makes the failed-login path constant-ish regardless of which
    credential was wrong.
    """
    return hash_password("OpenWrt-AI-Copilot timing-equalization dummy")


def _verify_or_dummy(password: str, stored_hash: str | None) -> bool:
    return verify_password(password, stored_hash or _timing_dummy_hash())


@router.post("/auth/login", summary="Sign in with an admin or read-only username")
async def login(request: Request, body: LoginRequest) -> dict:
    """Authenticate a browser user against a stored account and mint a session.

    Looks up the normalized username and compares the password to its stored
    bcrypt hash. Unknown users run the same hashing comparison against a dummy
    hash so failures are timing-uniform; invalid credentials are rejected
    without revealing which field was wrong. Returns a short-lived, revocable
    session token; credentials are never returned.
    """
    role = None
    user = _user_store(request).get_by_username(normalize_username(body.username))

    if user is not None and _verify_or_dummy(body.password, user.password_hash):
        role = user.role

    if role is None:
        await asyncio.sleep(0.3)  # throttle password-style guessing
        raise _INVALID_CREDENTIALS

    scopes = ADMIN_SCOPES if role == "admin" else READ_SCOPES
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