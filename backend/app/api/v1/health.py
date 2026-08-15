"""Health and readiness endpoints used by probes, load balancers, and the UI."""

from fastapi import APIRouter

from app.core.config import settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict:
    """Liveness probe: the service is up and serving requests."""
    return {
        "status": "ok",
        "service": settings.app_name,
        "version": settings.app_version,
        "environment": settings.environment,
        "git_commit": settings.git_commit or None,
        "build_date": settings.build_date or None,
    }


@router.get("/ready")
def ready() -> dict:
    """Readiness probe: the service is ready to accept traffic."""
    return {"status": "ready"}
