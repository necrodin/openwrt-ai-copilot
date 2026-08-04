"""Onboarding helpers: verify SSH connectivity and identify an OpenWrt device.

These run directly against the router using the router-agent SSH transport.
Connection failures are mapped to human-readable messages for the wizard UI.
"""

from __future__ import annotations

import logging

from router_agent.collectors import select_collectors
from router_agent.collectors.base import CollectorContext
from router_agent.config import AgentConfig
from router_agent.model import DeviceSnapshot
from router_agent.snapshot import build_snapshot
from router_agent.transport.base import CommandRunner
from router_agent.transport.ssh import (
    AuthenticationError,
    HostKeyError,
    SSHError,
    SSHTransport,
)
from router_agent.transport.ssh import (
    ConnectionError as SSHConnectionError,
)
from router_agent.transport.ssh import (
    TimeoutError as SSHTimeoutError,
)
from router_agent.transport.ubus import UbusClient

logger = logging.getLogger(__name__)

_DETAIL_COLLECTORS = frozenset({"kernel", "cpu", "memory", "network", "wifi", "packages"})


class DeviceDetectionError(Exception):
    """The device answered SSH but does not look like an OpenWrt router."""


def _human_error(exc: BaseException) -> str:
    """Turn a low-level SSH exception into a friendly, actionable message."""
    if isinstance(exc, AuthenticationError):
        return "Authentication failed — check the username and password or key."
    if isinstance(exc, HostKeyError):
        return "Host key verification failed — the device's SSH identity changed."
    if isinstance(exc, SSHTimeoutError):
        return "Connection timed out — is SSH enabled on the device?"
    if isinstance(exc, SSHConnectionError):
        return f"Could not connect to the device: {exc}"
    if isinstance(exc, SSHError):
        return f"SSH connection failed: {exc}"
    return f"Unexpected error: {exc}"


def friendly_error(exc: BaseException) -> str:
    """Public alias for :func:`_human_error` used by the API layer."""
    return _human_error(exc)


def _connect(
    *, host: str, port: int, username: str, password: str | None, private_key: str | None
) -> SSHTransport:
    return SSHTransport(
        host,
        port=port,
        username=username,
        password=password or None,
        private_key=private_key or None,
        command_timeout=20.0,
        host_key_policy="auto",
    )


def _best_effort(runner: CommandRunner, command: str) -> str | None:
    """Run a command and return its trimmed stdout, or None if it fails."""
    try:
        return runner.run(command).strip()
    except Exception:  # noqa: BLE001 - detection is best-effort
        return None


def _parse_release_description(text: str) -> str | None:
    """Extract ``DISTRIB_DESCRIPTION`` from an ``/etc/openwrt_release`` file."""
    for line in text.splitlines():
        if line.startswith("DISTRIB_DESCRIPTION="):
            value = line.split("=", 1)[1].strip().strip("'\"")
            return value or None
    return None


def _collect_snapshot(
    transport: SSHTransport, host: str, device_id: str
) -> DeviceSnapshot:
    """Build a real snapshot reusing the router-agent collectors.

    Only the sections the onboarding wizard renders are collected so a single
    SSH session answers both the connectivity check and the device summary.
    """
    config = AgentConfig(
        device_id=device_id or host,
        host=host,
        enabled_collectors=_DETAIL_COLLECTORS,
    )
    ubus = UbusClient(transport, timeout=20.0)
    ctx = CollectorContext(runner=transport, ubus=ubus, config=config)
    return build_snapshot(
        ctx,
        select_collectors(config),
        device_id=device_id or host,
        transport="ssh",
        host=host,
    )


def _detail_from_snapshot(snapshot: DeviceSnapshot) -> dict:
    """Map a collected snapshot onto the onboarding wizard summary fields."""
    cpu = snapshot.cpu
    memory = snapshot.memory
    used_percent = None
    if memory is not None and memory.total_kb:
        used_percent = round((memory.used_kb / memory.total_kb) * 100.0, 1)
    return {
        "kernel": snapshot.kernel.kernel or None,
        "architecture": snapshot.kernel.architecture or None,
        "cpu": {
            "cores": cpu.cores if cpu else None,
            "usage_percent": cpu.usage_percent if cpu else None,
            "load_1": cpu.load_1 if cpu else None,
        },
        "memory": {
            "total_kb": memory.total_kb if memory else None,
            "used_kb": memory.used_kb if memory else None,
            "used_percent": used_percent,
        },
        "network_interfaces": [
            {
                "name": interface.name,
                "up": interface.up,
                "proto": interface.proto,
                "mac": interface.mac,
                "link": interface.link,
                "addresses": [
                    {
                        "address": address.address,
                        "prefix": address.prefix,
                        "family": address.family,
                    }
                    for address in interface.addresses
                ],
            }
            for interface in snapshot.network
        ],
        "wifi_radios": [
            {
                "name": radio.name,
                "up": radio.up,
                "mode": radio.mode,
                "band": radio.band,
                "channel": radio.channel,
                "frequency_mhz": radio.frequency_mhz,
                "tx_power": radio.tx_power,
                "ssid": radio.ssid,
                "station_count": radio.station_count,
            }
            for radio in snapshot.wifi.radios
        ],
        "packages_count": len(snapshot.packages),
    }


def probe_connection(
    *,
    host: str,
    port: int,
    username: str,
    password: str | None = None,
    private_key: str | None = None,
) -> dict:
    """Open an SSH session and confirm the device answers commands."""
    transport = _connect(
        host=host, port=port, username=username, password=password, private_key=private_key
    )
    try:
        output = _best_effort(transport, "echo ok")
        if output != "ok":
            return {"ok": False, "error": "Device did not answer the connectivity check."}
        return {"ok": True, "error": None}
    finally:
        transport.close()


def detect_device(
    *,
    host: str,
    port: int,
    username: str,
    password: str | None = None,
    private_key: str | None = None,
) -> dict:
    """Identify an OpenWrt device over SSH.

    Returns connection metadata plus device details (model, firmware, hostname,
    suggested device id) once the device answers and looks like OpenWrt.
    """
    transport = _connect(
        host=host, port=port, username=username, password=password, private_key=private_key
    )
    try:
        return _detect_with(transport, host)
    finally:
        transport.close()


def _detect_with(transport: SSHTransport, host: str) -> dict:
    ubus = UbusClient(transport, timeout=20.0)

    board = None
    raw_release: str | None = None
    try:
        board = ubus.call("system", "board")
    except Exception:  # noqa: BLE001 - device may not expose ubus
        board = None
    if board:
        release = board.get("release") or {}
        release_text = release.get("description")
        model = board.get("model")
        board_name = board.get("board_name")
    else:
        raw_release = _best_effort(transport, "cat /etc/openwrt_release")
        release_text = _parse_release_description(raw_release) if raw_release else None
        model = None
        board_name = None

    is_openwrt = bool(board or (raw_release and "OpenWrt" in raw_release))
    if not is_openwrt:
        raise DeviceDetectionError(
            "This device answered over SSH but does not look like an OpenWrt "
            "router (no ubus board info and no OpenWrt release file). "
            "Double-check the host address."
        )

    hostname = _best_effort(transport, "uci get system.@system[0].hostname") or _best_effort(
        transport, "hostname"
    )
    device_id = board_name or hostname or host
    return {
        "ok": True,
        "is_openwrt": True,
        "host": host,
        "model": model,
        "firmware": release_text,
        "hostname": hostname,
        "device_id": device_id,
        **_detail_from_snapshot(_collect_snapshot(transport, host, device_id)),
    }
