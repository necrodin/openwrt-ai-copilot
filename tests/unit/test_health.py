"""Health endpoint unit tests."""


def test_health_returns_ok(client) -> None:
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["service"] == "OpenWrt AI Copilot"
    assert body["version"] == "0.1.0"


def test_ready_returns_ready(client) -> None:
    response = client.get("/api/v1/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


def test_openapi_schema_exposed(client) -> None:
    response = client.get("/api/openapi.json")

    assert response.status_code == 200
    schema = response.json()
    assert schema["info"]["title"] == "OpenWrt AI Copilot"
    assert "/api/v1/health" in schema["paths"]
