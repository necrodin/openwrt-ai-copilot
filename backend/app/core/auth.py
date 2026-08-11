"""Application-level authentication and authorization.

Security Fix #1: a small, self-contained auth boundary for the self-hosted
HTTP API. It implements scoped authentication as an application-level
abstraction that can later be backed by OIDC/JWT without changing the call
sites (dependencies resolve to an :class:`AuthPrincipal`; swap the resolver to
verify JWTs and the routers stay the same).

Two operator-provided API keys are configured through environment variables
(never hardcoded, never logged, never returned by the API). These keys remain
the programmatic-client credential — scripts, CLI, and curl authenticate with
``Authorization: Bearer <key>``:

- ``AUTH_ADMIN_API_KEY``    — full access: reads + management/write actions.
- ``AUTH_READONLY_API_KEY`` — read-only access: status, dashboard, provider
  introspection, and copilot chat.

Browser users do not use a key. ``POST /auth/login`` authenticates a username
and password configured via ``AUTH_ADMIN_USERNAME/PASSWORD`` and
``AUTH_READONLY_USERNAME/PASSWORD`` (see ``app.api.v1.auth``) and exchanges
them for a scoped browser session; the browser never holds the master key.

Browser sessions are opaque, short-lived, server-side tokens
(:class:`SessionStore`). They carry exactly the scopes of the account that
minted them, expire after ``AUTH_SESSION_TTL`` seconds, and can be revoked on
logout. This makes a leaked browser token bounded (expiry) and revocable
(logout) — the two properties a permanent static key can never provide.

Clients authenticate with ``Authorization: Bearer <token>``. WebSocket
connections authenticate the same way — via the ``Authorization`` header or,
for browsers that cannot set headers on the WebSocket upgrade, the ``?token=``
query parameter. Because a URL leaks credentials into history and logs, only a
short-lived browser session token is ever accepted from the query string (a
permanent master key is rejected there, and the upgrade is gated on ``Origin``).

Fail-closed: when no key is configured or the presented token is unknown, the
request is rejected (401). Reads require any valid key; write/management
actions additionally require ``devices.write``.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import threading
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import Depends, HTTPException, Request, WebSocket, status

from app.core.config import settings

# Scopes mirror the RBAC naming in docs/ARCHITECTURE.md §13.4.
SCOPE_DEVICES_READ = "devices.read"
SCOPE_DEVICES_WRITE = "devices.write"
SCOPE_AI_CHAT = "ai.chat"
SCOPE_ADMIN = "admin"

READ_SCOPES = frozenset({SCOPE_DEVICES_READ, SCOPE_AI_CHAT})
ADMIN_SCOPES = frozenset(
    {SCOPE_DEVICES_READ, SCOPE_DEVICES_WRITE, SCOPE_AI_CHAT, SCOPE_ADMIN},
)


class AuthPrincipal:
    """Authenticated identity with its granted scopes.

    ``subject`` is a stable, opaque identity derived from the presented
    credential (one-way hash of the browser session token or static API key).
    Two distinct tokens/keys always yield distinct subjects, and the same
    credential always yields the same subject. It lets downstream services
    (chat history, RAG conversation memory) namespace per-principal state
    without ever exposing the raw token.
    """

    __slots__ = ("key_id", "scopes", "subject")

    def __init__(self, *, key_id: str, scopes: frozenset[str], subject: str | None = None) -> None:
        self.key_id = key_id
        self.scopes = scopes
        self.subject = subject

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def _credentials() -> dict[str, frozenset[str]]:
    """Map each configured key to its granted scopes. Admin wins on collision."""
    creds: dict[str, frozenset[str]] = {}
    if settings.auth_readonly_api_key:
        creds[settings.auth_readonly_api_key] = READ_SCOPES
    if settings.auth_admin_api_key:
        creds[settings.auth_admin_api_key] = ADMIN_SCOPES
    return creds


class SessionRecord:
    """Server-side record backing one browser session."""

    __slots__ = ("role", "scopes", "expires_at")

    def __init__(self, *, role: str, scopes: frozenset[str], expires_at: datetime) -> None:
        self.role = role
        self.scopes = scopes
        self.expires_at = expires_at


class SessionStore:
    """Thread-safe, in-memory registry of short-lived browser sessions.

    Sessions are opaque random tokens. The store is created per application
    (``create_app``) so tests get an isolated registry per app instance.
    Expired records are lazily swept on access. Nothing here is ever logged:
    tokens live only in this dict.
    """

    def __init__(self, ttl_seconds: int) -> None:
        self._ttl = max(60, int(ttl_seconds))
        self._sessions: dict[str, SessionRecord] = {}
        self._lock = threading.Lock()

    def ttl(self) -> int:
        return self._ttl

    def create(
        self,
        *,
        role: str,
        scopes: frozenset[str],
        expires_at: datetime | None = None,
    ) -> tuple[str, SessionRecord]:
        """Mint a new session token and record. ``expires_at`` overrides the TTL."""
        token = secrets.token_urlsafe(32)
        expires_at = expires_at or (datetime.now(UTC) + timedelta(seconds=self._ttl))
        record = SessionRecord(role=role, scopes=scopes, expires_at=expires_at)
        with self._lock:
            self._sweep_locked()
            self._sessions[token] = record
        return token, record

    def resolve(self, token: str) -> SessionRecord | None:
        """Return the session record for a live token, or ``None``."""
        with self._lock:
            self._sweep_locked()
            record = self._sessions.get(token)
            if record is None or record.expires_at <= datetime.now(UTC):
                self._sessions.pop(token, None)
                return None
            return record

    def revoke(self, token: str) -> bool:
        """Permanently invalidate a session. Returns ``True`` when found."""
        with self._lock:
            return self._sessions.pop(token, None) is not None

    def _sweep_locked(self) -> None:
        now = datetime.now(UTC)
        expired = [tok for tok, rec in self._sessions.items() if rec.expires_at <= now]
        for tok in expired:
            del self._sessions[tok]


def _subject(token: str, *, session: bool) -> str:
    """Stable one-way identity for a credential (never the raw token)."""
    digest = hashlib.sha256(token.encode("utf-8")).hexdigest()
    prefix = "session" if session else "key"
    return f"{prefix}:{digest}"


def validate_token(
    token: str | None,
    *,
    store: SessionStore | None = None,
) -> AuthPrincipal | None:
    """Resolve a presented token to a principal, or ``None`` when unknown.

    Browser session tokens are checked first (they carry role-scoped
    permissions and can expire/be revoked); static operator keys are checked
    second as a constant-time comparison. Fails closed: an empty token or a
    token matching nothing resolves to ``None``.
    """
    if not token:
        return None
    if store is not None:
        record = store.resolve(token)
        if record is not None:
            return AuthPrincipal(
                key_id=record.role,
                scopes=record.scopes,
                subject=_subject(token, session=True),
            )
    for key, scopes in _credentials().items():
        if hmac.compare_digest(key, token):
            key_id = "admin" if SCOPE_DEVICES_WRITE in scopes else "readonly"
            return AuthPrincipal(
                key_id=key_id,
                scopes=scopes,
                subject=_subject(token, session=False),
            )
    return None


def _bearer_token(headers) -> str | None:
    authorization = headers.get("Authorization", "")
    if authorization.lower().startswith("bearer "):
        token = authorization[7:].strip()
        if token:
            return token
    return None


_UNAUTHENTICATED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Not authenticated",
)
_FORBIDDEN = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="Insufficient permissions",
)


async def require_authentication(request: Request) -> AuthPrincipal:
    """Dependency: any authenticated caller (both roles, keys or sessions)."""
    store = getattr(request.app.state, "auth_sessions", None)
    principal = validate_token(_bearer_token(request.headers), store=store)
    if principal is None:
        raise _UNAUTHENTICATED
    return principal


async def require_read(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_authentication)],
) -> AuthPrincipal:
    """Dependency: authenticated caller permitted to read router state."""
    if not principal.has_scope(SCOPE_DEVICES_READ):
        raise _FORBIDDEN
    return principal


async def require_write(
    request: Request,
    principal: Annotated[AuthPrincipal, Depends(require_authentication)],
) -> AuthPrincipal:
    """Dependency: authenticated caller permitted to mutate the router."""
    if not principal.has_scope(SCOPE_DEVICES_WRITE):
        raise _FORBIDDEN
    return principal


def _origin_allowed(websocket: WebSocket) -> bool:
    """Gate WebSocket upgrades on the ``Origin`` header.

    Browsers always send ``Origin`` on a WebSocket upgrade; native clients
    typically do not. A missing origin is therefore allowed, but a present
    origin must be in the configured CORS allow-list. This stops a malicious
    website from opening a socket to a token-bearing URL (e.g. one the victim
    pasted or that leaked into a referrer). ``CORSMiddleware`` only governs
    HTTP, so WebSockets need this check independently.
    """
    origin = websocket.headers.get("origin")
    if not origin:
        return True
    return "*" in settings.cors_origins or origin in settings.cors_origins


def authenticate_websocket(
    websocket: WebSocket,
    *,
    required_scope: str = SCOPE_DEVICES_READ,
) -> bool:
    """Validate a WebSocket upgrade before the socket is accepted.

    Accepts the bearer token from the ``Authorization`` header (non-browser
    clients) or the ``?token=`` query parameter (browsers). Credentials in a
    URL are exposed to browser history, server logs, and shared links, so the
    query parameter only ever resolves short-lived, revocable browser session
    tokens from the session store — a permanent static operator key is never
    accepted there. The upgrade additionally requires an allowed ``Origin``
    when present. Returns ``True`` only when the caller is authenticated and
    holds ``required_scope``.
    """
    if not _origin_allowed(websocket):
        return False
    store = getattr(websocket.app.state, "auth_sessions", None)

    token = _bearer_token(websocket.headers)
    if token is not None:
        # Header credentials are kept out of URLs, so non-browser clients may
        # present either a session token or a static operator key.
        principal = validate_token(token, store=store)
    else:
        # URL-visible credentials are bounded to short-lived sessions: a query
        # token is accepted only if it is a live session in this store.
        query_token = websocket.query_params.get("token")
        if not query_token or store is None:
            return False
        record = store.resolve(query_token)
        if record is None:
            return False
        principal = AuthPrincipal(
            key_id=record.role,
            scopes=record.scopes,
            subject=_subject(query_token, session=True),
        )
    return principal is not None and principal.has_scope(required_scope)
