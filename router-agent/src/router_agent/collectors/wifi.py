"""WiFi collector.

Combines the live ``ubus call wifi status`` view (radio operating state and
associated stations) with the configured UCI wireless tree (``uci show
wireless``), so the snapshot carries both the *configured* SSIDs — including
disabled ones — and the *live* radios and station metrics.
"""

from __future__ import annotations

import re
from typing import Any

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import WifiClient, WifiInfo, WifiNetwork, WifiRadio

_WIDTH = re.compile(r"(20|40|80|160|320)")

_KNOWN_WIDTHS = {20: 20, 40: 40, 80: 80, 160: 160, 320: 320}

_SECTION_LINE = re.compile(r"^wireless\.(?P<key>[^=]+)=(?P<type>[A-Za-z0-9_-]+)$")
_OPTION_LINE = re.compile(r"^wireless\.(?P<key>[^=]+)\.(?P<option>\w+)='(?P<value>[^']*)'$")

_STATION_LINE = re.compile(r"^Station\s+([0-9a-f:]{17})")


def _band(hwmode: str | None, frequency: int | None) -> str | None:
    if frequency is not None:
        return "5GHz" if frequency >= 5000 else "2.4GHz"
    if hwmode:
        mode = hwmode.lower()
        if "a" in mode:
            return "5GHz"
        if "b" in mode or "g" in mode:
            return "2.4GHz"
        if "ax" in mode or "ac" in mode:
            return "unknown"
    return None


def _width_mhz(htmode: str | None, hwmode: str | None) -> int | None:
    """Derive the channel width in MHz from the HT/VHT/HE/EHT mode.

    ``htmode`` values look like ``HT40``, ``VHT80``, ``HE160`` or ``EHT320``;
    the numeric part is the width in MHz.
    """
    if not htmode:
        if hwmode and "n" in hwmode.lower():
            return 20
        return None
    match = _WIDTH.search(htmode)
    if match:
        return _KNOWN_WIDTHS.get(int(match.group(1)))
    return None


def _as_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _parse_uci_wireless(text: str) -> tuple[dict[str, dict], list[dict]]:
    """Parse ``uci show wireless`` into (device configs, wifi-iface configs)."""
    sections: dict[str, dict] = {}
    for line in text.splitlines():
        line = line.strip()
        m = _OPTION_LINE.match(line)
        if m:
            key, option, value = m.group("key"), m.group("option"), m.group("value")
            sections.setdefault(key, {})[option] = value
            continue
        m = _SECTION_LINE.match(line)
        if m:
            sections.setdefault(m.group("key"), {"_type": m.group("type")})

    devices: dict[str, dict] = {}
    ifaces: list[dict] = []
    for key, section in sections.items():
        stype = section.get("_type")
        if stype == "wifi-device":
            devices[section.get("name", key)] = section
        elif stype == "wifi-iface":
            ifaces.append({**section, "_section": key})
    return devices, ifaces


def _count_iface_stations(ctx: CollectorContext, ifname: str) -> int:
    """Number of associated stations on one interface via ``iw``."""
    output = ctx.sh(f"iw dev {ifname} station dump 2>/dev/null", default="")
    return sum(1 for line in output.splitlines() if _STATION_LINE.match(line.strip()))


class WifiCollector(Collector):
    name = "wifi"

    def collect(self, ctx: CollectorContext) -> WifiInfo:
        try:
            status = ctx.ubus.call("wifi", "status")
        except Exception:  # noqa: BLE001
            status = {}

        devices, ifaces = _parse_uci_wireless(ctx.sh("uci show wireless", default=""))

        # Match configured wifi-ifaces to live ubus interfaces by device+ssid so
        # each SSID picks up its real interface name (needed for station counts).
        live_ifaces: dict[tuple[str, str], str] = {}
        radio_ifnames: dict[str, set[str]] = {}
        for radio_name, radio in status.items():
            if not isinstance(radio, dict):
                continue
            for iface in radio.get("interfaces") or []:
                if not isinstance(iface, dict):
                    continue
                iface_config = iface.get("config") or {}
                device = iface_config.get("device")
                ssid = iface_config.get("ssid")
                ifname = iface_config.get("ifname")
                if device and ssid and ifname:
                    live_ifaces[(device, ssid)] = ifname
                    radio_ifnames.setdefault(radio_name, set()).add(ifname)

        radios: list[WifiRadio] = []
        networks: list[WifiNetwork] = []
        clients: list[WifiClient] = []
        counted: set[tuple[str, str]] = set()

        for radio_name, radio in status.items():
            if not isinstance(radio, dict):
                continue
            config = radio.get("config") or {}
            interfaces = radio.get("interfaces") or []
            ssid = None
            for iface in interfaces:
                iface_config = (iface or {}).get("config") or {}
                if iface_config.get("ssid"):
                    ssid = iface_config.get("ssid")
                    break

            uci_device = devices.get(radio_name) or {}
            hwmode = uci_device.get("hwmode") or config.get("hwmode")
            htmode = uci_device.get("htmode") or config.get("htmode")
            frequency = _as_int(config.get("frequency"))
            channel = _as_int(uci_device.get("channel") or config.get("channel"))
            tx_power = _as_int(uci_device.get("txpower") or config.get("txpower"))

            stations = radio.get("stations") or {}
            station_count = len(stations) if isinstance(stations, dict) else 0
            radio_interfaces = sorted(radio_ifnames.get(radio_name, set()))
            station_ifname = radio_interfaces[0] if len(radio_interfaces) == 1 else None

            radios.append(
                WifiRadio(
                    name=radio_name,
                    up=bool(radio.get("up", False)),
                    mode=config.get("mode"),
                    band=_band(hwmode, frequency),
                    channel=channel,
                    frequency_mhz=frequency,
                    tx_power=tx_power,
                    ssid=ssid,
                    hwmode=hwmode,
                    width_mhz=_width_mhz(htmode, hwmode),
                    station_count=station_count,
                    country=uci_device.get("country") or config.get("country"),
                    hardware=uci_device.get("path"),
                )
            )

            for mac, station in (stations or {}).items():
                if not isinstance(station, dict):
                    continue
                signal = _as_int(station.get("signal"))
                connected = _as_int(station.get("connected_time"))
                clients.append(
                    WifiClient(
                        mac=mac,
                        ssid=ssid,
                        signal_dbm=signal,
                        tx_bytes=_as_int(station.get("txbytes")),
                        rx_bytes=_as_int(station.get("rxbytes")),
                        connected_minutes=connected,
                        noise=_as_int(station.get("noise")),
                        rx_rate=_as_int(station.get("rx_rate")),
                        tx_rate=_as_int(station.get("tx_rate")),
                        interface=station_ifname,
                        connected_time=connected,
                    )
                )

        for iface in ifaces:
            ssid = iface.get("ssid", "")
            device = iface.get("device", "")
            ifname = live_ifaces.get((device, ssid))
            client_count = 0
            if ifname and device and ssid:
                counted.add((device, ssid))
                client_count = _count_iface_stations(ctx, ifname)
            networks.append(
                WifiNetwork(
                    ssid=ssid,
                    radio=device,
                    interface=ifname,
                    mode=iface.get("mode"),
                    encryption=iface.get("encryption"),
                    hidden=iface.get("hidden") == "1",
                    enabled=iface.get("disabled") != "1",
                    network=iface.get("network"),
                    client_count=client_count,
                    section=iface["_section"],
                )
            )

        return WifiInfo(radios=radios, networks=networks, clients=clients)
