"""Chat request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ChatRequestBody(BaseModel):
    session_id: str = Field(default="default", min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=20_000)
    provider: str | None = None
    model: str | None = None
    temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    router_aware: bool = False
