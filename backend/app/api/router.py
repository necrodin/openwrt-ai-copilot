"""Aggregated API router mounted under the configured API prefix."""

from fastapi import APIRouter, Depends

from app.api.v1 import (
    auth,
    chat,
    client_labels,
    dashboard,
    health,
    management,
    onboarding,
    providers,
    router_status,
    setup,
)
from app.api.v1 import router as router_endpoints
from app.core.auth import require_read

api_router = APIRouter()

# Public: liveness probes for load balancers, the operator-login endpoint
# (login exchanges a key for a session; session/logout guard themselves), and
# first-run administrator setup (status probe + admin creation). Setup works
# only while no user exists; once users table is populated it fails closed.
api_router.include_router(health.router, prefix="/v1")
api_router.include_router(auth.router, prefix="/v1")
api_router.include_router(setup.router, prefix="/v1")
# Every other v1 surface is authenticated. Dashboard is included without a
# router-level guard because its WebSocket validates the caller itself.
api_router.include_router(providers.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(dashboard.router, prefix="/v1")
api_router.include_router(router_status.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(
    router_endpoints.router, prefix="/v1", dependencies=[Depends(require_read)]
)
api_router.include_router(onboarding.router, prefix="/v1", dependencies=[Depends(require_read)])
# Client labels: the router-level guard covers reads (devices.read); the
# individual write endpoints additionally require devices.write.
api_router.include_router(
    client_labels.router, prefix="/v1", dependencies=[Depends(require_read)]
)
api_router.include_router(management.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(chat.router, prefix="/v1", dependencies=[Depends(require_read)])
