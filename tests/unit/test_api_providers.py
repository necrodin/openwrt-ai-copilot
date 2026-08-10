"""Providers admin API tests (dependency-overridden manager, no network)."""

from __future__ import annotations

import json

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.provider_manager import get_provider_manager
from providers.factory import ProviderManager
from providers.openai import OpenAIProvider
from tests.auth import admin_headers
from tests.unit.providers_helpers import make_provider

MODELS = {"data": [{"id": "gpt-4o-mini"}, {"id": "text-embedding-3-small"}]}


def _manager() -> ProviderManager:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=MODELS)
        if request.url.path.endswith("/chat/completions"):
            body = json.loads(request.content)
            return httpx.Response(
                200,
                json={
                    "model": body["model"],
                    "choices": [{"message": {"role": "assistant", "content": "hi"}}],
                    "usage": {"prompt_tokens": 3, "completion_tokens": 1},
                },
            )
        return httpx.Response(404)

    return ProviderManager(
        {"primary": make_provider(OpenAIProvider, handler, name="primary", model="gpt-4o-mini")},
        default_provider="primary",
    )


@pytest.fixture()
def api_client() -> TestClient:
    app = create_app()
    app.dependency_overrides[get_provider_manager] = _manager
    with TestClient(app, headers=admin_headers()) as test_client:
        yield test_client


def test_list_providers(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers")
    assert response.status_code == 200
    body = response.json()
    assert body["default_provider"] == "primary"
    assert body["providers"][0]["name"] == "primary"
    assert body["providers"][0]["type"] == "openai"
    assert "chat" in body["providers"][0]["static_capabilities"]


def test_provider_detail(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/primary")
    assert response.status_code == 200
    assert response.json()["type"] == "openai"


def test_provider_not_found(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/nope")
    assert response.status_code == 404


def test_provider_health(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/primary/health")
    assert response.status_code == 200
    assert response.json() == {"name": "primary", "healthy": True}


def test_provider_capabilities(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/primary/capabilities")
    assert response.status_code == 200
    body = response.json()
    assert "chat" in body["capabilities"]
    assert body["static"] is False  # runtime catalog probe contributed models


def test_provider_usage_empty(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/primary/usage")
    assert response.status_code == 200
    assert response.json()["usage"]["calls"] == 0


def test_provider_models(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/primary/models")
    assert response.status_code == 200
    ids = [model["id"] for model in response.json()["models"]]
    assert "gpt-4o-mini" in ids


def test_provider_models_error_maps_to_502(api_client: TestClient) -> None:
    app = create_app()
    manager = ProviderManager(
        {"broken": make_provider(OpenAIProvider, lambda _: httpx.Response(503))}
    )
    app.dependency_overrides[get_provider_manager] = lambda: manager
    with TestClient(app, headers=admin_headers()) as test_client:
        response = test_client.get("/api/v1/providers/broken/models")
    assert response.status_code == 502
