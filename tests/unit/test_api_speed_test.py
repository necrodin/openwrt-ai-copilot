"""Speed-test API tests.

A fake ``SpeedTestService`` is injected into the app state so the endpoints are
exercised deterministically: success, hard failure/timeout, partial
(incomplete) results, concurrent/cooldown gating, and authentication.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.speed_test import SpeedTestBusy, SpeedTestCooldown, SpeedTestError
from tests.auth import admin_headers, readonly_headers

RESULT = {
    "download_mbps": 245.4,
    "upload_mbps": 38.2,
    "ping_ms": 12.4,
    "jitter_ms": 2.8,
    "timestamp": "2026-08-14T00:00:00Z",
    "duration_ms": 12345,
    "limitations": [],
    "complete": True,
}


class FakeSpeedTestService:
    """Minimal stand-in for :class:`SpeedTestService` API tests."""

    def __init__(self, *, result=None, error=None, latest_value=None) -> None:
        self._result = result
        self._error = error
        self._latest = latest_value
        self.run_calls = 0

    def latest(self):
        return self._latest

    def run(self):
        self.run_calls += 1
        if self._error is not None:
            raise self._error
        return self._result


@contextmanager
def client_with_service(service: FakeSpeedTestService) -> Iterator[TestClient]:
    app = create_app()
    app.state.speed_test_service = service
    with TestClient(app, headers=admin_headers()) as client:
        yield client


def test_run_speed_test_returns_measured_values() -> None:
    service = FakeSpeedTestService(result=RESULT)
    with client_with_service(service) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 200
    assert response.json() == RESULT
    assert service.run_calls == 1


def test_run_speed_test_hard_failure_maps_to_502() -> None:
    error = SpeedTestError("Could not reach latency target 1.1.1.1:443.")
    service = FakeSpeedTestService(error=error)
    with client_with_service(service) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 502
    assert "latency target" in response.json()["detail"]


def test_run_speed_test_timeout_maps_to_502() -> None:
    service = FakeSpeedTestService(error=SpeedTestError("timed out"))
    with client_with_service(service) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 502
    assert response.json()["detail"] == "timed out"


def test_partial_incomplete_measurement_returns_200() -> None:
    partial = {
        **RESULT,
        "upload_mbps": None,
        "complete": False,
        "limitations": ["Upload could not be measured: timed out"],
    }
    service = FakeSpeedTestService(result=partial)
    with client_with_service(service) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 200
    body = response.json()
    assert body["upload_mbps"] is None
    assert body["download_mbps"] == 245.4
    assert body["complete"] is False
    assert body["limitations"]


def test_concurrent_run_returns_409() -> None:
    service = FakeSpeedTestService(error=SpeedTestBusy("A speed test is already running."))
    with client_with_service(service) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 409


def test_cooldown_run_returns_429() -> None:
    error = SpeedTestCooldown("A speed test ran too recently; try again shortly.")
    service = FakeSpeedTestService(error=error)
    with client_with_service(service) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 429


def test_latest_returns_result_when_present() -> None:
    service = FakeSpeedTestService(latest_value=RESULT)
    with client_with_service(service) as client:
        response = client.get("/api/v1/network/speed-test")
    assert response.status_code == 200
    assert response.json() == {"result": RESULT}


def test_latest_returns_null_before_first_run() -> None:
    with client_with_service(FakeSpeedTestService()) as client:
        response = client.get("/api/v1/network/speed-test")
    assert response.status_code == 200
    assert response.json() == {"result": None}


def test_endpoints_require_authentication() -> None:
    app = create_app()
    app.state.speed_test_service = FakeSpeedTestService(result=RESULT)
    with TestClient(app) as client:  # no auth headers
        assert client.post("/api/v1/network/speed-test").status_code == 401
        assert client.get("/api/v1/network/speed-test").status_code == 401


def test_readonly_role_can_run_speed_test() -> None:
    app = create_app()
    app.state.speed_test_service = FakeSpeedTestService(result=RESULT)
    with TestClient(app, headers=readonly_headers()) as client:
        response = client.post("/api/v1/network/speed-test")
    assert response.status_code == 200
    assert response.json()["download_mbps"] == 245.4
