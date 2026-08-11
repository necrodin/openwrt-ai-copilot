"""First-run administrator setup.

OpenWrt AI Copilot is self-hosted: the very first browser visit creates the
administrator account. These two public endpoints drive that flow:

- ``GET  /setup/status`` — reports whether setup is required (no users yet).
- ``POST /setup/admin``  — creates the first (and only) administrator.

``POST /setup/admin`` validates the submitted credentials against a documented
minimum policy, hashes the password with bcrypt (never stores plaintext),
creates the admin account race-safely (``INSERT ... WHERE NOT EXISTS`` plus a
partial unique index on ``role='admin'``), then mints the normal short-lived
browser session: after setup the user lands directly in the console, exactly as
after a login. Once any user exists the endpoint fails closed with 409 and the
admin account can never be created twice.

After setup completes, ``GET /setup/status`` reports ``setup_required: false``
forever and the page switches to the normal login flow. Programmatic clients
are unaffected (API-key headers, WebSocket/SSE auth, and chat isolation all
continue to use the existing session/static-token boundary).
"""

from __future__ import annotations

import re

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, field_validator, model_validator

from app.core.auth import ADMIN_SCOPES, SessionStore
from app.core.passwords import (
    BCRYPT_MAX_BYTES,
    hash_password,
    normalize_username,
)
from app.db.user_store import UserStore
from app.db.user_store import store as default_user_store

router = APIRouter(tags=["setup"])

#: Minimum credential policy — documented and enforced on setup. Usernames are
#: 3-64 characters of letters/digits/``.``/``-``/``_``; passwords are 8-72
#: characters (72 is bcrypt's hard input limit, enforced in bytes below).
_MIN_USERNAME = 3
_MAX_USERNAME = 64
_MIN_PASSWORD = 8
_USERNAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

_SETUP_COMPLETE = HTTPException(
    status_code=status.HTTP_409_CONFLICT,
    detail="Setup has already been completed.",
)


class SetupStatusResponse(BaseModel):
    setup_required: bool


class SetupAdminRequest(BaseModel):
    username: str = Field(min_length=1, max_length=_MAX_USERNAME)
    password: str = Field(min_length=_MIN_PASSWORD, max_length=BCRYPT_MAX_BYTES)
    confirm_password: str = Field(min_length=_MIN_PASSWORD, max_length=BCRYPT_MAX_BYTES)

    @field_validator("username")
    @classmethod
    def _validate_username(cls, value: str) -> str:
        normalized = normalize_username(value)
        if len(normalized) < _MIN_USERNAME or len(normalized) > _MAX_USERNAME:
            raise ValueError(
                f"Username must be {_MIN_USERNAME}-{_MAX_USERNAME} characters."
            )
        if not _USERNAME_RE.fullmatch(normalized):
            raise ValueError(
                "Username may only contain letters, digits, dots, dashes, "
                "and underscores."
            )
        return normalized

    @field_validator("password")
    @classmethod
    def _validate_password(cls, value: str) -> str:
        if len(value.encode("utf-8")) > BCRYPT_MAX_BYTES:
            raise ValueError("Password is too long.")
        return value

    @model_validator(mode="after")
    def _confirm_matches(self) -> SetupAdminRequest:
        if self.password != self.confirm_password:
            raise ValueError("Passwords do not match.")
        return self


def _user_store(request: Request) -> UserStore:
    return getattr(request.app.state, "user_store", None) or default_user_store


@router.get(
    "/setup/status",
    summary="Whether first-run administrator setup is required",
    response_model=SetupStatusResponse,
)
def setup_status(request: Request) -> SetupStatusResponse:
    """Public probe the frontend uses to choose the setup vs. login page."""
    return SetupStatusResponse(setup_required=_user_store(request).setup_required())


@router.post(
    "/setup/admin",
    summary="Create the initial administrator account",
)
async def setup_admin(request: Request, body: SetupAdminRequest) -> dict:
    """Create the first and only administrator and open a browser session.

    Fails closed (409) once any user exists; the account is created in a single
    atomic statement so simultaneous requests cannot create two admins. The
    password is bcrypt-hashed and discarded; only the hash is stored. On
    success the response is identical to ``POST /auth/login``: a short-lived,
    revocable session token that enters the application immediately.
    """
    store = _user_store(request)
    if not store.setup_required():
        raise _SETUP_COMPLETE

    created = store.insert_admin(
        username=body.username,
        password_hash=hash_password(body.password),
    )
    if not created:
        # Another request won the first-run race; setup now fails closed.
        raise _SETUP_COMPLETE

    role = "admin"
    auth_store: SessionStore = request.app.state.auth_sessions
    token, record = auth_store.create(role=role, scopes=ADMIN_SCOPES)
    return {
        "token": token,
        "role": role,
        "expires_at": record.expires_at.isoformat(),
        "ttl_seconds": auth_store.ttl(),
    }