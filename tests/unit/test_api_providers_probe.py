"""Draft provider probe API tests (test + model discovery before saving).

The endpoints are admin-scoped; the underlying diagnostics are mocked so no
network is touched. Focus: request mapping, categorized results, and that
neither credentials nor env-var names leak into responses.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from tests.auth import admin_headers, readonly_headers


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "provider_config_file", str(tmp_path / "providers.yaml"))
    app = create_app()
    with TestClient(app, headers=admin_headers()) as test_client:
        yield test_client


def _probe() -> dict:
    return {
        "type": "compat",
        "name": "Draft",
        "base_url": "https://example.com/v1",
        "api_key_env": "MY_AI_KEY",
        "model": "some-model",
    }


def test_draft_test_runs_and_returns_categorized_result(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import app.api.v1.providers as providers_module

    async def fake_test(cfg) -> dict:
        assert cfg.type == "compat"
        assert cfg.base_url == "https://example.com/v1"
        assert cfg.model == "some-model"
        # Env-var NAME travels server-side only; the value must not be needed.
        assert cfg.api_key_env == "MY_AI_KEY"
        return {
            "ok": True,
            "category": "ok",
            "message": "Connection OK — the configured model answered a test prompt.",
            "model": "some-model",
            "reply": "OK",
            "latency_ms": 42,
        }

    monkeypatch.setattr(providers_module, "test_provider_chat", fake_test)
    response = client.post("/api/v1/providers/test", json=_probe())
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["category"] == "ok"
    assert "MY_AI_KEY" not in json.dumps(body)


def test_draft_test_failure_category_surfaces(client: TestClient, monkeypatch) -> None:
    import app.api.v1.providers as providers_module

    async def fake_test(cfg) -> dict:
        return {"ok": False, "category": "authentication_failed", "message": "bad key"}

    monkeypatch.setattr(providers_module, "test_provider_chat", fake_test)
    response = client.post("/api/v1/providers/test", json=_probe())
    assert response.status_code == 200
    assert response.json()["category"] == "authentication_failed"


def test_draft_discover_models(client: TestClient, monkeypatch) -> None:
    import app.api.v1.providers as providers_module

    async def fake_discover(cfg) -> dict:
        assert cfg.base_url == "https://example.com/v1"
        return {
            "ok": True,
            "models": [{"id": "m1", "capabilities": ["chat"], "context_window": None}],
        }

    monkeypatch.setattr(providers_module, "discover_provider_models", fake_discover)
    response = client.post("/api/v1/providers/discover-models", json=_probe())
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["models"][0]["id"] == "m1"


def test_draft_probe_invalid_type_rejected(client: TestClient) -> None:
    body = {**_probe(), "type": "not-real"}
    assert client.post("/api/v1/providers/test", json=body).status_code == 400
    assert client.post("/api/v1/providers/discover-models", json=body).status_code == 400


def test_draft_probe_invalid_config_rejected(client: TestClient) -> None:
    # compat without a base_url fails config validation (422).
    body = {**_probe(), "base_url": None}
    response = client.post("/api/v1/providers/test", json=body)
    assert response.status_code == 422


def test_draft_probe_requires_admin_write(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "provider_config_file", str(tmp_path / "providers.yaml"))
    with TestClient(create_app(), headers=readonly_headers()) as reader:
        assert reader.post("/api/v1/providers/test", json=_probe()).status_code == 403
        assert (
            reader.post("/api/v1/providers/discover-models", json=_probe()).status_code == 403
        )
