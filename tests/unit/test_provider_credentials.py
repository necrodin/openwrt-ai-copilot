"""Provider credential storage tests: encrypted at rest, write-only API.

Covers the secure-credential model: the operator enters the ACTUAL API key,
the backend encrypts it into its own credential store (never providers.yaml),
responses/logs never contain it, and the empty-credential edit semantics are
enforced server-side. Legacy ``api_key_env`` resolution keeps working.
"""

from __future__ import annotations

import json
import logging
import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import create_app
from app.services import provider_diagnostics
from app.services.provider_credentials import store_path
from app.services.provider_manager import read_provider_config
from providers.base import resolve_api_key
from providers.config import ProviderConfig
from providers.factory import create_provider
from providers.transport import ProviderTransport
from tests.auth import admin_headers
from tests.unit.providers_helpers import make_mock_client


@pytest.fixture()
def api_client(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(settings, "provider_config_file", str(tmp_path / "providers.yaml"))
    app = create_app()
    with TestClient(app, headers=admin_headers()) as client:
        yield client


def _create(client: TestClient, type_: str = "openai", **extra) -> object:
    return client.post("/api/v1/providers", json={"type": type_, **extra})


def _config_yaml() -> str:
    return pathlib.Path(settings.provider_config_file).read_text(encoding="utf-8")


# ── create with a direct credential ────────────────────────────────────────


def test_create_with_credential_is_write_only_and_encrypted(api_client: TestClient) -> None:
    secret = "sk-live-12345"
    response = _create(api_client, credential=secret)
    assert response.status_code == 201
    body = response.json()
    assert body["has_credential"] is True
    assert secret not in json.dumps(body)

    # providers.yaml carries metadata only — never the key.
    assert secret not in _config_yaml()

    # The encrypted store holds ciphertext only.
    store_file = store_path(settings)
    assert store_file.is_file()
    raw = store_file.read_text(encoding="utf-8")
    assert secret not in raw
    assert "encv1:" in raw

    # GET responses never contain the key.
    listed = api_client.get("/api/v1/providers").json()
    assert secret not in json.dumps(listed)
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["has_credential"] is True
    assert "credential" not in openai


def test_credential_never_in_logs(api_client: TestClient) -> None:
    secret = "sk-log-secret-99"
    records: list[str] = []
    handler = logging.Handler()

    def emit(record: logging.LogRecord) -> None:
        records.append(record.getMessage())

    handler.emit = emit  # type: ignore[method-assign]
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        assert _create(api_client, credential=secret).status_code == 201
    finally:
        root.removeHandler(handler)
    assert "\n".join(records).find(secret) == -1


def test_stored_credential_resolves_from_saved_config(api_client: TestClient) -> None:
    """The runtime path (manager build) resolves the stored key via the resolver."""
    secret = "sk-stored-42"
    assert _create(api_client, credential=secret).status_code == 201
    cfg = read_provider_config().providers["openai"]
    assert cfg.api_key is None  # never carried in the saved config
    assert resolve_api_key(cfg) == secret


# ── diagnostics with a supplied (unsaved) credential ───────────────────────


def test_draft_probe_uses_unsaved_credential(api_client: TestClient, monkeypatch) -> None:
    import app.api.v1.providers as providers_module

    seen: dict[str, object] = {}

    async def fake_test(cfg) -> dict:
        seen["credential"] = cfg.api_key
        return {"ok": True, "category": "ok", "message": "ok"}

    monkeypatch.setattr(providers_module, "test_provider_chat", fake_test)
    response = api_client.post(
        "/api/v1/providers/test",
        json={
            "type": "openai",
            "base_url": "https://api.openai.com/v1",
            "model": "gpt-4o",
            "credential": "sk-unsaved-7",
        },
    )
    assert response.status_code == 200
    assert seen["credential"] == "sk-unsaved-7"
    assert "sk-unsaved-7" not in json.dumps(response.json())


def _chat_handler() -> tuple[dict, callable]:
    captured: dict[str, str | None] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["authorization"] = request.headers.get("authorization")
        if request.url.path.endswith("/chat/completions"):
            sse = (
                'data: {"model": "gpt-4o", "choices": '
                '[{"delta": {"content": "OK"}, "finish_reason": null}]}\n\n'
                'data: {"choices": [{"delta": {}, "finish_reason": "stop"}]}\n\n'
                "data: [DONE]\n\n"
            )
            return httpx.Response(
                200,
                content=sse,
                headers={"Content-Type": "text/event-stream"},
            )
        return httpx.Response(404)

    return captured, handler


def _diag_with_credential(cfg: ProviderConfig):
    captured, handler = _chat_handler()

    def fake_build(c: ProviderConfig):
        client = make_mock_client(handler)
        transport = ProviderTransport(
            base_url=c.effective_base_url(), api_key=c.api_key, client=client
        )
        return create_provider(c, transport=transport)

    provider_diagnostics.create_provider = fake_build  # type: ignore[attr-defined]
    return captured


def _cfg(**overrides) -> ProviderConfig:
    base = {"type": "openai", "base_url": "https://api.openai.com/v1", "model": "gpt-4o"}
    base.update(overrides)
    cfg = ProviderConfig(**base)
    return cfg


@pytest.mark.asyncio
async def test_successful_diagnostic_uses_supplied_credential() -> None:
    cfg = _cfg()
    cfg.api_key = "sk-supplied"
    captured = _diag_with_credential(cfg)

    result = await provider_diagnostics.test_provider_chat(cfg)

    assert result["ok"] is True
    assert result["category"] == "ok"
    assert captured["authorization"] == "Bearer sk-supplied"


@pytest.mark.asyncio
async def test_wrong_credential_is_authentication_failure() -> None:
    cfg = _cfg()
    cfg.api_key = "sk-wrong"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    def fake_build(c: ProviderConfig):
        client = make_mock_client(handler)
        transport = ProviderTransport(
            base_url=c.effective_base_url(), api_key=c.api_key, client=client
        )
        return create_provider(c, transport=transport)

    provider_diagnostics.create_provider = fake_build  # type: ignore[attr-defined]
    result = await provider_diagnostics.test_provider_chat(cfg)
    assert result["ok"] is False
    assert result["category"] == "authentication_failed"
    assert "sk-wrong" not in json.dumps(result)


# ── edit / remove / delete semantics ───────────────────────────────────────


def test_edit_without_credential_preserves_stored_credential(api_client: TestClient) -> None:
    secret = "sk-keep-me"
    assert _create(api_client, credential=secret).status_code == 201
    response = api_client.patch("/api/v1/providers/openai", json={"name": "Renamed"})
    assert response.status_code == 200
    assert response.json()["has_credential"] is True
    assert resolve_api_key(read_provider_config().providers["openai"]) == secret

    # An EXPLICIT empty credential also preserves it (server-side, not only UI).
    response = api_client.patch("/api/v1/providers/openai", json={"credential": ""})
    assert response.status_code == 200
    assert response.json()["has_credential"] is True
    assert resolve_api_key(read_provider_config().providers["openai"]) == secret


def test_edit_replaces_credential(api_client: TestClient) -> None:
    assert _create(api_client, credential="sk-old").status_code == 201
    response = api_client.patch("/api/v1/providers/openai", json={"credential": "sk-new"})
    assert response.status_code == 200
    assert resolve_api_key(read_provider_config().providers["openai"]) == "sk-new"
    store_file = store_path(settings).read_text(encoding="utf-8")
    assert "sk-old" not in store_file
    assert "sk-new" not in store_file


def test_remove_credential_endpoint(api_client: TestClient) -> None:
    assert _create(api_client, credential="sk-remove").status_code == 201
    response = api_client.delete("/api/v1/providers/openai/credential")
    assert response.status_code == 200
    assert response.json()["has_credential"] is False
    assert resolve_api_key(read_provider_config().providers["openai"]) is None
    listed = api_client.get("/api/v1/providers").json()
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["has_credential"] is False


def test_remove_credential_missing_provider_404(api_client: TestClient) -> None:
    assert api_client.delete("/api/v1/providers/openai/credential").status_code == 404


def test_delete_provider_deletes_credential(api_client: TestClient) -> None:
    assert _create(api_client, credential="sk-delete").status_code == 201
    assert api_client.delete("/api/v1/providers/openai").status_code == 200
    raw = store_path(settings).read_text(encoding="utf-8")
    assert "openai" not in json.loads(raw or "{}")


def test_disable_provider_preserves_credential(api_client: TestClient) -> None:
    secret = "sk-disabled"
    assert _create(api_client, credential=secret).status_code == 201
    api_client.post("/api/v1/providers/openai/disable")
    assert resolve_api_key(read_provider_config().providers["openai"]) == secret
    listed = api_client.get("/api/v1/providers").json()
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["enabled"] is False
    assert openai["has_credential"] is True


def test_multiple_providers_have_independent_credentials(api_client: TestClient) -> None:
    assert _create(api_client, type_="openai", credential="sk-a").status_code == 201
    assert _create(
        api_client,
        type_="openrouter",
        base_url="https://openrouter.ai/api/v1",
        model="gpt-oss-20b:free",
        credential="sk-b",
    ).status_code == 201
    providers = read_provider_config().providers
    assert resolve_api_key(providers["openai"]) == "sk-a"
    assert resolve_api_key(providers["openrouter"]) == "sk-b"


def test_legacy_api_key_env_still_works(api_client: TestClient, monkeypatch) -> None:
    monkeypatch.setenv("LEGACY_PROVIDER_KEY", "sk-env-1")
    assert _create(api_client, api_key_env="LEGACY_PROVIDER_KEY").status_code == 201
    assert resolve_api_key(read_provider_config().providers["openai"]) == "sk-env-1"
    listed = api_client.get("/api/v1/providers").json()
    openai = next(p for p in listed["providers"] if p["type"] == "openai")
    assert openai["has_credential"] is True
    assert "LEGACY_PROVIDER_KEY" not in json.dumps(listed)
