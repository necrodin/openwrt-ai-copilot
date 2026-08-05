"""Onboarding API tests: /router/test-connection, /router/detect, /router/save.

Real SSH is never attempted — the probe/detect service functions are
monkeypatched. The save flow is exercised against the throwaway test database
and the real SnapshotService, so we also verify the live feed switches to the
saved router.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.db.router_store import store as router_store
from app.services import onboarding as onboarding_service
from app.services.onboarding import DeviceDetectionError
from router_agent.transport.ssh import AuthenticationError, ConnectionError, TimeoutError


@pytest.fixture(autouse=True)
def _clean_routers(client: TestClient) -> None:
    """Tests assume an empty router table; the shared test DB persists per session."""
    for record in router_store.get_all():
        router_store.delete(record.id)
    yield


# ── /router/test-connection ───────────────────────────────────────────────────


def test_test_connection_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        onboarding_service,
        "probe_connection",
        lambda **kwargs: {"ok": True, "error": None},
    )
    response = client.post(
        "/api/v1/router/test-connection",
        json={"host": "192.168.1.1", "port": 22, "username": "root", "password": "secret"},
    )
    assert response.status_code == 200
    assert response.json() == {"ok": True, "error": None}


def test_test_connection_failure_is_friendly(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(**kwargs):
        raise AuthenticationError("mock: bad password")

    monkeypatch.setattr(onboarding_service, "probe_connection", boom)
    response = client.post(
        "/api/v1/router/test-connection",
        json={"host": "192.168.1.1", "username": "root", "password": "wrong"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert "Authentication failed" in body["error"]


@pytest.mark.parametrize(
    "exc, fragment",
    [
        (TimeoutError("mock timeout"), "timed out"),
        (ConnectionError("mock refused"), "Could not connect"),
        (DeviceDetectionError("no OpenWrt"), "no OpenWrt"),
    ],
)
def test_test_connection_error_mapping(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, exc: Exception, fragment: str
) -> None:
    def boom(**kwargs):
        raise exc

    monkeypatch.setattr(onboarding_service, "probe_connection", boom)
    response = client.post(
        "/api/v1/router/test-connection",
        json={"host": "192.168.1.1", "username": "root", "password": "x"},
    )
    assert response.json()["ok"] is False
    assert fragment in response.json()["error"]


def test_test_connection_validation_key_requires_secret(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/test-connection",
        json={"host": "192.168.1.1", "auth_type": "key", "private_key": None},
    )
    assert response.status_code == 422


# ── /router/detect ────────────────────────────────────────────────────────────


def test_detect_ok(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        onboarding_service,
        "detect_device",
        lambda **kwargs: {
            "ok": True,
            "is_openwrt": True,
            "host": "192.168.1.1",
            "model": "TP-Link Archer C7",
            "firmware": "OpenWrt 23.05.3",
            "hostname": "archer",
            "device_id": "archer-c7",
        },
    )
    response = client.post(
        "/api/v1/router/detect",
        json={"host": "192.168.1.1", "username": "root", "password": "secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["is_openwrt"] is True
    assert body["model"] == "TP-Link Archer C7"
    assert body["device_id"] == "archer-c7"


def test_detect_not_openwrt(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(**kwargs):
        raise DeviceDetectionError("not OpenWrt")

    monkeypatch.setattr(onboarding_service, "detect_device", boom)
    response = client.post(
        "/api/v1/router/detect",
        json={"host": "192.168.1.1", "username": "root", "password": "x"},
    )
    assert response.json()["ok"] is False
    assert "not OpenWrt" in response.json()["error"]


def test_detect_returns_onboarding_summary(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The detect endpoint exposes the rich summary the wizard renders."""
    monkeypatch.setattr(
        onboarding_service,
        "detect_device",
        lambda **kwargs: {
            "ok": True,
            "is_openwrt": True,
            "host": "192.168.1.1",
            "model": "TP-Link Archer C7",
            "firmware": "OpenWrt 23.05.3",
            "hostname": "archer",
            "device_id": "ar750",
            "kernel": "5.15.150",
            "architecture": "mips_24kc",
            "cpu": {"cores": 4, "usage_percent": 12.5, "load_1": 0.5},
            "memory": {"total_kb": 131072, "used_kb": 65536, "used_percent": 50.0},
            "network_interfaces": [
                {
                    "name": "lan",
                    "up": True,
                    "proto": "static",
                    "mac": "00:11:22:33:44:55",
                    "link": True,
                    "addresses": [{"address": "192.168.1.1", "prefix": 24, "family": "ipv4"}],
                }
            ],
            "wifi_radios": [
                {
                    "name": "radio0",
                    "up": True,
                    "mode": "ap",
                    "band": "2.4GHz",
                    "channel": 6,
                    "frequency_mhz": 2437,
                    "tx_power": 20,
                    "ssid": "HomeNet",
                    "station_count": 3,
                }
            ],
            "packages_count": 2,
        },
    )
    response = client.post(
        "/api/v1/router/detect",
        json={"host": "192.168.1.1", "username": "root", "password": "secret"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["kernel"] == "5.15.150"
    assert body["architecture"] == "mips_24kc"
    assert body["cpu"]["cores"] == 4
    assert body["memory"]["used_percent"] == 50.0
    assert body["network_interfaces"][0]["name"] == "lan"
    assert body["wifi_radios"][0]["ssid"] == "HomeNet"
    assert body["packages_count"] == 2


# ── /router/save + /router/connections ────────────────────────────────────────


def test_save_persists_and_switches_feed(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/save",
        json={
            "name": "Living Room",
            "host": "127.0.0.1",
            "port": 22,
            "username": "root",
            "auth_type": "password",
            "password": "topsecret",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == "Living Room"
    assert body["host"] == "127.0.0.1"
    assert body["id"] > 0
    assert "password" not in body

    assert client.app.state.snapshot_service.source == "ssh"
    assert client.app.state.snapshot_service.latest() is None

    listing = client.get("/api/v1/router/connections").json()
    routers = listing["routers"]
    assert len(routers) == 1
    saved = routers[0]
    assert saved["name"] == "Living Room"
    assert saved["host"] == "127.0.0.1"
    assert "password" not in saved
    assert "private_key" not in saved


def test_save_key_auth_stores_key(client: TestClient) -> None:
    private_key = "-----BEGIN OPENSSH PRIVATE KEY-----\nabc123\n-----END OPENSSH PRIVATE KEY-----\n"
    response = client.post(
        "/api/v1/router/save",
        json={
            "name": "Garage",
            "host": "127.0.0.1",
            "username": "root",
            "auth_type": "key",
            "private_key": private_key,
        },
    )
    assert response.status_code == 200
    saved = client.get("/api/v1/router/connections").json()["routers"]
    assert len(saved) == 1
    assert saved[0]["auth_type"] == "key"
    assert "private_key" not in saved[0]


def test_save_rejects_empty_name(client: TestClient) -> None:
    response = client.post(
        "/api/v1/router/save",
        json={"name": "", "host": "127.0.0.1", "username": "root", "password": "x"},
    )
    assert response.status_code == 422


def test_list_connections_empty(client: TestClient) -> None:
    body = client.get("/api/v1/router/connections").json()
    assert body == {"routers": []}


def test_delete_connection(client: TestClient) -> None:
    saved = client.post(
        "/api/v1/router/save",
        json={"name": "Temp", "host": "127.0.0.1", "username": "root", "password": "x"},
    ).json()
    delete = client.delete(f"/api/v1/router/connections/{saved['id']}")
    assert delete.status_code == 200
    assert delete.json() == {"ok": True}
    assert client.get("/api/v1/router/connections").json() == {"routers": []}


def test_delete_connection_missing(client: TestClient) -> None:
    response = client.delete("/api/v1/router/connections/9999")
    assert response.status_code == 404
