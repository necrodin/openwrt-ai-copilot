"""FastAPI application entrypoint.

Assembles the application shell: configuration, logging, CORS, database
initialization, authentication, the provider manager lifecycle, and the API
routers for auth, dashboard, chat, router management, and providers.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.api.router import api_router
from app.core.auth import SessionStore
from app.core.config import settings
from app.core.logging import configure_logging
from app.core.vault import ensure_credential_vault, harden_database_permissions
from app.db.chat_store import store as chat_store
from app.db.client_label_store import store as client_label_store
from app.db.router_store import store as router_store
from app.db.user_store import bootstrap_env_credentials
from app.db.user_store import store as user_store_store
from app.services.chat_service import ChatService
from app.services.provider_manager import load_provider_manager
from app.services.rag_service import load_rag_service
from app.services.router_management import RouterManagementService
from app.services.router_manager import RouterManager
from app.services.router_tool import RouterTool
from app.services.snapshot_service import RouterConnection, SnapshotService
from app.services.speed_test import SpeedTestService
from database.session import init_db

#: Authenticated state prefixes that must never be cached by a browser/shared
#: cache: router state + management reads, dashboard state, chat history.
_SENSITIVE_NO_STORE_PREFIXES = (
    "/api/v1/router/",
    "/api/v1/dashboard/",
    "/api/v1/chat/",
)


class _NoStoreSensitive(BaseHTTPMiddleware):
    """Set ``Cache-Control: no-store`` on sensitive authenticated reads.

    Responses that already declare a cache directive (the chat SSE stream's
    ``no-cache`` and the artifact download's ``no-store``) are left untouched.
    """

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        sensitive = request.url.path.startswith(_SENSITIVE_NO_STORE_PREFIXES)
        if sensitive and "cache-control" not in response.headers:
            response.headers["Cache-Control"] = "no-store"
        return response


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_logging(level=settings.log_level)
    init_db()
    # Optional one-time migration for installations configured with the legacy
    # environment credentials: seed the first stored accounts from
    # AUTH_ADMIN_USERNAME/PASSWORD (and the readonly pair) so existing browser
    # logins keep working. Runs only while the users table is empty; afterwards
    # stored accounts are authoritative and the env values are ignored.
    if application.state.env_bootstrap_enabled:
        bootstrap_env_credentials(application.state.user_store)
    # Configure the credential vault before any router record is read or written:
    # encryption-at-rest for new credentials and a one-time migration of legacy
    # plaintext. Fails fast when stored credentials need a key that is missing.
    vault = ensure_credential_vault(settings, router_store)
    harden_database_permissions(settings.database_url)
    # Encrypted provider API-key store (same vault key). Keys are never stored
    # in providers.yaml; the store also feeds the provider factory's credential
    # resolver so live providers authenticate with the stored key.
    from app.services.provider_credentials import build_store, configure_store

    credential_store = build_store(settings, vault)
    configure_store(credential_store)
    application.state.provider_credentials = credential_store
    application.state.provider_manager = load_provider_manager()
    snapshot_service = SnapshotService()
    # If a router was configured previously (onboarding), reconnect to it so the
    # dashboard and chat resume with real data across restarts.
    saved = router_store.get_most_recent()
    if saved is not None:
        snapshot_service.configure_connection(
            RouterConnection(
                host=saved.host,
                port=saved.port,
                username=saved.username,
                password=saved.password,
                private_key=saved.private_key,
                device_id=saved.device_id,
            )
        )
    application.state.snapshot_service = snapshot_service
    snapshot_service.start()
    application.state.management_service = RouterManagementService(
        resolve_connection=lambda: application.state.snapshot_service.active_connection,
    )
    application.state.chat_store = chat_store
    router_manager = RouterManager()
    router_manager.register("default", RouterTool(snapshot_service.latest), default=True)
    application.state.router_manager = router_manager
    application.state.chat_service = ChatService(
        application.state.provider_manager,
        snapshot=lambda: (
            snapshot_service.latest().snapshot if snapshot_service.latest() is not None else None
        ),
        router_manager=router_manager,
    )
    # RAG chat is opt-in: ``rag.yaml`` present -> grounded, cited chat is
    # enabled; missing/unparseable -> existing router-state chat stays active.
    application.state.rag_service = await load_rag_service(application.state.provider_manager)
    try:
        yield
    finally:
        if application.state.rag_service is not None:
            await application.state.rag_service.aclose()
        await snapshot_service.stop()
        await application.state.provider_manager.aclose()


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Provider-independent AI copilot for OpenWrt router fleets.",
        docs_url="/api/docs",
        redoc_url="/api/redoc",
        openapi_url="/api/openapi.json",
        lifespan=lifespan,
    )

    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Sensitive authenticated state endpoints (router state, dashboard, chat
    # history) must not be cached by browsers or shared caches. Endpoints that
    # already set an explicit cache directive (e.g. the SSE stream's no-cache
    # and the artifact download's no-store) keep their own header.
    application.add_middleware(_NoStoreSensitive)  # type: ignore[arg-type]

    # Server-side browser sessions (login/logout). Created here, outside the
    # lifespan, so the auth boundary works even for apps started without the
    # full service lifecycle (e.g. lightweight test clients).
    application.state.auth_sessions = SessionStore(settings.auth_session_ttl)

    # Application-user accounts (first-run setup + browser login). Bound to the
    # default store here so endpoints can resolve it from app state; tests swap
    # in an isolated store to exercise fresh-installation flows deterministically.
    application.state.user_store = user_store_store
    application.state.env_bootstrap_enabled = True

    # Client device labels (per-MAC operator labels). Bound here so endpoints
    # resolve it from app state; tests can swap in an isolated store.
    application.state.client_label_store = client_label_store

    # Management job -> creating-principal index (see api.v1.management).
    # Kept per-application so tests get an isolated registry per app instance.
    application.state.management_job_owners = {}

    # In-memory internet speed-test service (latest result + run gate). Bound
    # to the app instance so tests get an isolated copy.
    application.state.speed_test_service = SpeedTestService()

    application.include_router(api_router, prefix=settings.api_prefix)

    return application


app = create_app()
