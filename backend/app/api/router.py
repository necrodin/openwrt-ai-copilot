"""Aggregated API router mounted under the configured API prefix."""

from fastapi import APIRouter

from app.api.v1 import chat, dashboard, health, providers

api_router = APIRouter()

api_router.include_router(health.router, prefix="/v1")
api_router.include_router(providers.router, prefix="/v1")
api_router.include_router(dashboard.router, prefix="/v1")
api_router.include_router(chat.router, prefix="/v1")
