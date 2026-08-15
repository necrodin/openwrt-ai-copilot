"""Provider configuration-management API tests.

These exercise the real file-backed path (config reads/writes + manager
reload), so each test points ``settings.provider_config_file`` at a throwaway
file. The read-only introspection endpoints are unchanged and covered in
``test_api_providers.py``; here we focus on the admin-guarded mutations.
"""

from __future__ import annotations

import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from tests.auth import admin_headers, readonly_headers


@pytest.fixture()
def api_client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "provider_config_file", str(tmp_path / "providers.yaml"))
    app = create_app()
    with TestClient(app, headers=admin_headers()) as test_client:
        yield test_client


def _create(client: TestClient, type_: str = "openai", **extra) -> object:
    body = {"type": type_, **extra}
    return client.post("/api/v1/providers", json=body)


def test_create_provider_persists_and_loads(api_client: TestClient) -> None:
    response = _create(api_client)
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "openai"
    assert body["enabled"] is True

    listed = api_client.get("/api/v1/providers").json()
    assert any(p["type"] == "openai" for p in listed["providers"])

    persisted = pathlib.Path(settings.provider_config_file).read_text()
    assert "providers:" in persisted
    assert "openai:" in persisted


def test_create_unsupported_type_rejected(api_client: TestClient) -> None:
    response = _create(api_client, type_="not-a-real-provider")
    assert response.status_code == 400


def test_create_invalid_fields_rejected(api_client: TestClient) -> None:
    response = _create(api_client, timeout_seconds="nope")
    assert response.status_code == 422


def test_create_duplicate_conflict(api_client: TestClient) -> None:
    assert _create(api_client).status_code == 201
    response = _create(api_client)
    assert response.status_code == 409


def test_edit_provider(api_client: TestClient) -> None:
    _create(api_client)
    response = api_client.patch(
        "/api/v1/providers/openai",
        json={"name": "My OpenAI", "base_url": "http://example.test/v1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "My OpenAI"

    detail = api_client.get("/api/v1/providers/openai").json()
    assert detail["name"] == "My OpenAI"
    assert detail["base_url"] == "http://example.test/v1"


def test_edit_missing_provider_404(api_client: TestClient) -> None:
    response = api_client.patch("/api/v1/providers/openai", json={"name": "x"})
    assert response.status_code == 404


def test_enable_disable_provider(api_client: TestClient) -> None:
    _create(api_client)
    disabled = api_client.post("/api/v1/providers/openai/disable").json()
    assert disabled["enabled"] is False

    # Disabled providers remain visible in the list (marked disabled) so they
    # can be re-enabled from the UI.
    listed = api_client.get("/api/v1/providers").json()
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["enabled"] is False
    assert openai["is_default"] is False

    enabled = api_client.post("/api/v1/providers/openai/enable").json()
    assert enabled["enabled"] is True
    listed = api_client.get("/api/v1/providers").json()
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["enabled"] is True


def test_set_default_provider(api_client: TestClient) -> None:
    _create(api_client)
    response = api_client.post("/api/v1/providers/default", json={"type": "openai"})
    assert response.status_code == 200
    assert response.json()["default_provider"] == "openai"
    assert api_client.get("/api/v1/providers").json()["default_provider"] == "openai"


def test_set_default_disabled_provider_rejected(api_client: TestClient) -> None:
    _create(api_client)
    api_client.post("/api/v1/providers/openai/disable")
    response = api_client.post("/api/v1/providers/default", json={"type": "openai"})
    assert response.status_code == 400


def test_set_default_missing_provider_404(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/providers/default", json={"type": "openai"})
    assert response.status_code == 404


def test_delete_provider_clears_default(api_client: TestClient) -> None:
    _create(api_client)
    api_client.post("/api/v1/providers/default", json={"type": "openai"})
    response = api_client.delete("/api/v1/providers/openai")
    assert response.status_code == 200
    assert response.json()["deleted"] is True

    assert api_client.get("/api/v1/providers/openai").status_code == 404
    persisted = pathlib.Path(settings.provider_config_file).read_text()
    assert "openai:" not in persisted
    assert "default_provider" not in persisted


def test_delete_missing_provider_404(api_client: TestClient) -> None:
    response = api_client.delete("/api/v1/providers/openai")
    assert response.status_code == 404


def test_list_reports_model_and_credential_flag_only(api_client: TestClient) -> None:
    response = _create(api_client, model="gpt-4o-mini", api_key_env="MY_OPENAI_KEY")
    assert response.status_code == 201
    listed = api_client.get("/api/v1/providers").json()
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["model"] == "gpt-4o-mini"
    # The env-var NAME is never exposed; only a boolean credential flag is.
    assert openai["has_credential"] is True
    assert "api_key_env" not in openai


def test_create_custom_openai_compatible_provider(api_client: TestClient) -> None:
    """The always-available custom type accepts a base URL, model, credential."""
    response = _create(
        api_client,
        type_="compat",
        name="My AI",
        base_url="https://example.com/v1",
        model="some-model",
        api_key_env="MY_AI_KEY",
    )
    assert response.status_code == 201
    body = response.json()
    assert body["type"] == "compat"
    assert body["name"] == "My AI"
    assert body["base_url"] == "https://example.com/v1"
    assert body["model"] == "some-model"
    assert body["has_credential"] is True

    persisted = pathlib.Path(settings.provider_config_file).read_text()
    assert "api_key_env: MY_AI_KEY" in persisted


def test_create_compat_without_base_url_rejected(api_client: TestClient) -> None:
    response = _create(api_client, type_="compat", model="m")
    assert response.status_code == 422


def test_create_provider_with_custom_base_url(api_client: TestClient) -> None:
    response = _create(
        api_client,
        type_="azure_openai",
        base_url="https://my-resource.openai.azure.com/openai/v1",
        model="gpt-4o",
    )
    assert response.status_code == 201
    assert response.json()["base_url"] == "https://my-resource.openai.azure.com/openai/v1"


def test_edit_preserves_configured_credential(api_client: TestClient) -> None:
    _create(api_client, api_key_env="MY_OPENAI_KEY")
    response = api_client.patch(
        "/api/v1/providers/openai",
        json={"name": "Renamed", "model": "gpt-4o"},
    )
    assert response.status_code == 200
    assert response.json()["has_credential"] is True
    detail = api_client.get("/api/v1/providers/openai").json()
    assert detail["has_credential"] is True
    assert detail["model"] == "gpt-4o"
    assert "MY_OPENAI_KEY" not in json.dumps(detail)


def test_edit_replaces_credential_when_new_env_name_supplied(api_client: TestClient) -> None:
    _create(api_client, api_key_env="OLD_KEY")
    response = api_client.patch("/api/v1/providers/openai", json={"api_key_env": "NEW_KEY"})
    assert response.status_code == 200
    assert response.json()["has_credential"] is True
    persisted = pathlib.Path(settings.provider_config_file).read_text()
    assert "OLD_KEY" not in persisted
    assert "api_key_env: NEW_KEY" in persisted


def test_types_list_includes_custom_and_labels(api_client: TestClient) -> None:
    response = api_client.get("/api/v1/providers/types")
    assert response.status_code == 200
    types = {t["type"]: t for t in response.json()["types"]}
    assert "compat" in types
    assert types["compat"]["label"] == "Custom / OpenAI-compatible"
    assert types["compat"]["requires_base_url"] is True
    assert types["openai"]["label"] == "OpenAI"
    assert types["azure_openai"]["label"] == "Azure OpenAI"
    assert types["groq"]["label"] == "Groq"
    assert "default_base_url" in types["openai"]
    assert "MY_OPENAI_KEY" not in str(api_client.get("/api/v1/providers").text)


def test_disabled_provider_detail_is_described_from_config(api_client: TestClient) -> None:
    _create(api_client, model="llama")
    api_client.post("/api/v1/providers/openai/disable")
    response = api_client.get("/api/v1/providers/openai")
    assert response.status_code == 200
    body = response.json()
    assert body["enabled"] is False
    assert body["model"] == "llama"
    assert body["type"] == "openai"


def test_test_connection_runs_model_test(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _create(api_client, model="gpt-4o")

    import app.api.v1.providers as providers_module

    async def fake_test(cfg) -> dict:
        assert cfg.model == "gpt-4o"
        return {"ok": True, "category": "ok", "message": "Connection OK"}

    monkeypatch.setattr(providers_module, "test_provider_chat", fake_test)

    response = api_client.post("/api/v1/providers/openai/test")
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert response.json()["category"] == "ok"


def test_test_connection_missing_provider_404(api_client: TestClient) -> None:
    response = api_client.post("/api/v1/providers/openai/test")
    assert response.status_code == 404


def test_mutations_require_authentication(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "provider_config_file", str(tmp_path / "providers.yaml"))
    app = create_app()
    bodied = {
        ("post", "/api/v1/providers"): {"type": "openai"},
        ("post", "/api/v1/providers/default"): {"type": "openai"},
        ("post", "/api/v1/providers/test"): {"type": "openai", "model": "gpt-4o"},
        ("post", "/api/v1/providers/discover-models"): {"type": "openai"},
        ("patch", "/api/v1/providers/openai"): {"name": "x"},
    }
    audience = [
        ("post", "/api/v1/providers"),
        ("post", "/api/v1/providers/default"),
        ("post", "/api/v1/providers/test"),
        ("post", "/api/v1/providers/discover-models"),
        ("post", "/api/v1/providers/openai/enable"),
        ("post", "/api/v1/providers/openai/disable"),
        ("post", "/api/v1/providers/openai/test"),
        ("patch", "/api/v1/providers/openai"),
        ("delete", "/api/v1/providers/openai"),
    ]
    with TestClient(app) as anon_client:  # no auth headers
        for method, path in audience:
            response = anon_client.request(method, path, json=bodied.get((method, path)))
            assert response.status_code == 401, (method, path)


def test_mutations_require_admin_write_scope(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Read-auto test client for the create so the provider exists before we
    # attempt admin-only mutations as a reader.
    monkeypatch.setattr(settings, "provider_config_file", str(tmp_path / "providers.yaml"))
    app = create_app()
    with TestClient(app, headers=admin_headers()) as admin_client:
        assert _create(admin_client).status_code == 201
    with TestClient(create_app(), headers=readonly_headers()) as readonly_client:
        audience = [
            ("post", "/api/v1/providers/test"),
            ("post", "/api/v1/providers/discover-models"),
            ("post", "/api/v1/providers/openai/enable"),
            ("post", "/api/v1/providers/openai/disable"),
            ("post", "/api/v1/providers/openai/test"),
            ("patch", "/api/v1/providers/openai"),
            ("delete", "/api/v1/providers/openai"),
        ]
        for method, path in audience:
            response = readonly_client.request(method, path)
            assert response.status_code == 403, (method, path)
    # Reads remain available to the reader role.
    with TestClient(create_app(), headers=readonly_headers()) as readonly_client:
        assert readonly_client.get("/api/v1/providers").status_code == 200
