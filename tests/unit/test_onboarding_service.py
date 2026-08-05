"""Onboarding service tests: probe_connection and detect_device (no real SSH).

A fake transport is injected via ``_connect``/``UbusClient`` so the detection
logic (ubus first, /etc/openwrt_release fallback) is covered end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.services import onboarding as svc
from app.services.onboarding import DeviceDetectionError
from router_agent.model import (
    CpuInfo,
    DeviceSnapshot,
    KernelInfo,
    MemoryInfo,
    NetworkAddress,
    NetworkInterface,
    Package,
    SnapshotMeta,
    WifiInfo,
    WifiRadio,
)
from router_agent.transport.ssh import (
    AuthenticationError,
    ConnectionError,
    HostKeyError,
    TimeoutError,
)


class FakeTransport:
    """CommandRunner stand-in with scripted responses by command prefix."""

    def __init__(self, responses: dict[str, str] | None = None) -> None:
        self.responses = responses or {}
        self.closed = False
        self.commands: list[str] = []

    def run(self, command: str, *, timeout: float | None = None) -> str:
        self.commands.append(command)
        for prefix, output in self.responses.items():
            if command.startswith(prefix):
                return output
        raise RuntimeError(f"unscripted command: {command}")

    def close(self) -> None:
        self.closed = True


class FakeUbus:
    """Minimal stand-in for the real UbusClient."""

    def __init__(
        self,
        runner,
        *,
        timeout: float,
        board: dict | None,
        error: Exception | None = None,
    ):
        self._board = board
        self._error = error

    def call(self, object_: str, method: str, params: dict | None = None) -> dict:
        if self._error is not None:
            raise self._error
        if self._board is not None:
            return self._board
        raise RuntimeError("no board")

    @property
    def timeout(self) -> float:  # pragma: no cover
        return 0


@pytest.fixture()
def use_fakes(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Install fake transport/ubus factories and record created transports."""
    created: list[FakeTransport] = []

    def fake_connect(**kwargs):
        transport = FakeTransport(
            {
                "echo ok": "ok\n",
                "cat /etc/openwrt_release": (
                    "DISTRIB_ID='OpenWrt'\nDISTRIB_DESCRIPTION='OpenWrt 23.05.3'\n"
                ),
                "uci get system.@system[0].hostname": "archer\n",
                "hostname": "archer\n",
            }
        )
        created.append(transport)
        return transport

    monkeypatch.setattr(svc, "_connect", fake_connect)
    return {"created": created}


# ── probe_connection ──────────────────────────────────────────────────────────


def test_probe_ok(use_fakes: dict) -> None:
    result = svc.probe_connection(host="192.168.1.1", port=22, username="root", password="pw")
    assert result == {"ok": True, "error": None}
    assert use_fakes["created"][0].closed is True


def test_probe_answer_wrong(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(svc, "_connect", lambda **kwargs: FakeTransport({"echo ok": "busy\n"}))
    result = svc.probe_connection(host="h", port=22, username="root", password="pw")
    assert result["ok"] is False
    assert "did not answer" in result["error"]


# ── detect_device ─────────────────────────────────────────────────────────────


def test_detect_via_ubus(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport({"uci get system.@system[0].hostname": "archer\n"})
    monkeypatch.setattr(svc, "_connect", lambda **kwargs: transport)

    def fake_ubus(runner, *, timeout, board=None, error=None, **_kwargs):
        return FakeUbus(
            runner,
            timeout=timeout,
            board={
                "model": "TP-Link Archer C7",
                "board_name": "ar750",
                "release": {"description": "OpenWrt 23.05.3", "version": "23.05.3"},
            },
        )

    monkeypatch.setattr(svc, "UbusClient", fake_ubus)
    result = svc.detect_device(host="192.168.1.1", port=22, username="root", password="pw")
    assert result["ok"] is True
    assert result["is_openwrt"] is True
    assert result["model"] == "TP-Link Archer C7"
    assert result["firmware"] == "OpenWrt 23.05.3"
    assert result["hostname"] == "archer"
    assert result["device_id"] == "ar750"
    assert transport.closed is True


def test_detect_falls_back_to_release_file(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport(
        {
            "cat /etc/openwrt_release": "DISTRIB_DESCRIPTION='OpenWrt 22.03'\n",
            "hostname": "node1\n",
        }
    )
    monkeypatch.setattr(svc, "_connect", lambda **kwargs: transport)
    monkeypatch.setattr(
        svc,
        "UbusClient",
        lambda runner, *, timeout, **_kwargs: FakeUbus(runner, timeout=timeout, board=None),
    )
    result = svc.detect_device(host="h", port=22, username="root", password="pw")
    assert result["ok"] is True
    assert result["is_openwrt"] is True
    assert result["firmware"] == "OpenWrt 22.03"
    assert result["device_id"] == "node1"


def test_detect_not_openwrt_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport({"cat /etc/openwrt_release": "Unknown firmware\n"})
    monkeypatch.setattr(svc, "_connect", lambda **kwargs: transport)
    monkeypatch.setattr(
        svc,
        "UbusClient",
        lambda runner, *, timeout, **_kwargs: FakeUbus(runner, timeout=timeout, board=None),
    )
    with pytest.raises(DeviceDetectionError):
        svc.detect_device(host="h", port=22, username="root", password="pw")


def test_detect_ubus_error_falls_through(monkeypatch: pytest.MonkeyPatch) -> None:
    transport = FakeTransport({"hostname": "x\n"})
    monkeypatch.setattr(svc, "_connect", lambda **kwargs: transport)
    monkeypatch.setattr(
        svc,
        "UbusClient",
        lambda runner, *, timeout, **_kwargs: FakeUbus(
            runner, timeout=timeout, board=None, error=RuntimeError("ubus down")
        ),
    )
    with pytest.raises(DeviceDetectionError):
        svc.detect_device(host="h", port=22, username="root", password="pw")


# ── rich device summary ────────────────────────────────────────────────────────


def _make_snapshot() -> DeviceSnapshot:
    return DeviceSnapshot(
        meta=SnapshotMeta(
            collected_at=datetime.now(UTC), device_id="ar750", transport="ssh", host="192.168.1.1"
        ),
        kernel=KernelInfo(
            kernel="5.15.150",
            hostname="archer",
            model="TP-Link Archer C7",
            architecture="mips_24kc",
            board="ar750",
            release="OpenWrt 23.05.3",
        ),
        cpu=CpuInfo(load_1=0.5, load_5=0.4, load_15=0.3, cores=4, usage_percent=12.5),
        memory=MemoryInfo(total_kb=131072, free_kb=65536, used_kb=65536),
        network=[
            NetworkInterface(
                name="lan",
                up=True,
                proto="static",
                mac="00:11:22:33:44:55",
                link=True,
                addresses=[NetworkAddress(address="192.168.1.1", prefix=24, family="ipv4")],
            )
        ],
        wifi=WifiInfo(
            radios=[
                WifiRadio(
                    name="radio0",
                    up=True,
                    mode="ap",
                    band="2.4GHz",
                    channel=6,
                    frequency_mhz=2437,
                    tx_power=20,
                    ssid="HomeNet",
                    station_count=3,
                )
            ]
        ),
        packages=[
            Package(name="luci", version="23.05.3-1"),
            Package(name="wpad", version="2023-09-29"),
        ],
    )


def test_detect_returns_rich_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    """The detect response includes the Step-3 wizard fields (no mock data)."""
    transport = FakeTransport({"uci get system.@system[0].hostname": "archer\n"})
    monkeypatch.setattr(svc, "_connect", lambda **kwargs: transport)

    snapshot = _make_snapshot()
    monkeypatch.setattr(svc, "_collect_snapshot", lambda *a, **k: snapshot)

    def fake_ubus(runner, *, timeout, board=None, error=None, **_kwargs):
        return FakeUbus(
            runner,
            timeout=timeout,
            board={
                "model": "TP-Link Archer C7",
                "board_name": "ar750",
                "release": {"description": "OpenWrt 23.05.3", "version": "23.05.3"},
            },
        )

    monkeypatch.setattr(svc, "UbusClient", fake_ubus)
    result = svc.detect_device(host="192.168.1.1", port=22, username="root", password="pw")

    assert result["kernel"] == "5.15.150"
    assert result["architecture"] == "mips_24kc"
    assert result["cpu"] == {
        "cores": 4,
        "usage_percent": 12.5,
        "load_1": 0.5,
    }
    assert result["memory"] == {
        "total_kb": 131072,
        "used_kb": 65536,
        "used_percent": 50.0,
    }
    assert result["network_interfaces"] == [
        {
            "name": "lan",
            "up": True,
            "proto": "static",
            "mac": "00:11:22:33:44:55",
            "link": True,
            "addresses": [{"address": "192.168.1.1", "prefix": 24, "family": "ipv4"}],
        }
    ]
    assert result["wifi_radios"] == [
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
    ]
    assert result["packages_count"] == 2


def test_detail_from_snapshot_handles_empty_sections() -> None:
    """Missing sections map to nulls instead of crashing the wizard."""
    snapshot = DeviceSnapshot(
        meta=SnapshotMeta(collected_at=datetime.now(UTC), device_id="d", transport="ssh", host="h"),
    )
    detail = svc._detail_from_snapshot(snapshot)
    assert detail["kernel"] is None
    assert detail["architecture"] is None
    assert detail["cpu"] == {"cores": None, "usage_percent": None, "load_1": None}
    assert detail["memory"] == {
        "total_kb": None,
        "used_kb": None,
        "used_percent": None,
    }
    assert detail["network_interfaces"] == []
    assert detail["wifi_radios"] == []
    assert detail["packages_count"] == 0


# ── error mapping ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "exc, fragment",
    [
        (AuthenticationError("bad"), "Authentication failed"),
        (HostKeyError("mismatch"), "Host key"),
        (TimeoutError("timeout"), "timed out"),
        (ConnectionError("refused"), "Could not connect"),
        (ValueError("boom"), "Unexpected error"),
    ],
)
def test_human_error(exc: BaseException, fragment: str) -> None:
    assert fragment in svc.friendly_error(exc)
