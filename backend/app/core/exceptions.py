"""Application exception hierarchy and FastAPI error handlers.

Sprint 1 foundation: base classes only. Handlers are added as the API surface
grows in later sprints.
"""

from fastapi import Request
from fastapi.responses import JSONResponse


class AppError(Exception):
    """Base class for all application errors."""


class ConfigurationError(AppError):
    """Invalid or missing configuration."""


class DatabaseError(AppError):
    """Database operation failed."""


class NotFoundError(AppError):
    """Requested resource does not exist."""


async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={"error": {"code": exc.__class__.__name__, "message": str(exc)}},
    )


async def not_found_handler(_: Request, exc: NotFoundError) -> JSONResponse:
    return JSONResponse(
        status_code=404,
        content={"error": {"code": "NotFoundError", "message": str(exc)}},
    )
