"""Aggregated API router mounted under the configured API prefix."""

from fastapi import APIRouter, Depends

from app.api.v1 import (
    auth,
    chat,
    dashboard,
    health,
    management,
    onboarding,
    providers,
    router_status,
)
from app.api.v1 import router as router_endpoints
from app.core.auth import require_read

api_router = APIRouter()

# Public: liveness probes for load balancers and the operator-login endpoint
# (login exchanges a key for a session; session/logout guard themselves).
api_router.include_router(health.router, prefix="/v1")
api_router.include_router(auth.router, prefix="/v1")
# Every other v1 surface is authenticated. Dashboard is included without a
# router-level guard because its WebSocket validates the caller itself.
api_router.include_router(providers.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(dashboard.router, prefix="/v1")
api_router.include_router(router_status.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(
    router_endpoints.router, prefix="/v1", dependencies=[Depends(require_read)]
)
api_router.include_router(onboarding.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(management.router, prefix="/v1", dependencies=[Depends(require_read)])
api_router.include_router(chat.router, prefix="/v1", dependencies=[Depends(require_read)])
