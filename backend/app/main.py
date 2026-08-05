"""FastAPI application entrypoint.

Sprint 1 scope: application shell, configuration, logging, CORS, database
initialization, and a health API. Sprint 2 adds the provider manager lifecycle
and provider admin endpoints. No router logic or RAG yet.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import api_router
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.chat_store import store as chat_store
from app.db.router_store import store as router_store
from app.services.chat_service import ChatService
from app.services.provider_manager import load_provider_manager
from app.services.rag_service import load_rag_service
from app.services.router_management import RouterManagementService
from app.services.router_manager import RouterManager
from app.services.router_tool import RouterTool
from app.services.snapshot_service import RouterConnection, SnapshotService
from database.session import init_db


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    configure_logging(level=settings.log_level)
    init_db()
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

    application.include_router(api_router, prefix=settings.api_prefix)

    return application


app = create_app()
