"""Onboarding request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field, model_validator


def _require_secret_for_key(data: dict) -> dict:
    if data.get("auth_type") == "key" and not (data.get("password") or data.get("private_key")):
        raise ValueError("private key is required when auth_type is 'key'")
    return data


class RouterTestRequest(BaseModel):
    """Credentials to try connecting to a router."""

    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="root", min_length=1, max_length=128)
    auth_type: str = Field(default="password", pattern="^(password|key)$")
    password: str | None = Field(default=None, max_length=4096)
    private_key: str | None = Field(default=None, max_length=32_768)

    @model_validator(mode="after")
    def _auth_needs_secret(self) -> RouterTestRequest:
        _require_secret_for_key(self.model_dump())
        return self


class RouterSaveRequest(BaseModel):
    """Final onboarding payload; persisted so the app reconnects on restart."""

    name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(default="root", min_length=1, max_length=128)
    auth_type: str = Field(default="password", pattern="^(password|key)$")
    password: str | None = Field(default=None, max_length=4096)
    private_key: str | None = Field(default=None, max_length=32_768)

    @model_validator(mode="after")
    def _auth_needs_secret(self) -> RouterSaveRequest:
        _require_secret_for_key(self.model_dump())
        return self
