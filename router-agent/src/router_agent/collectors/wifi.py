"""WiFi collector.

Source: ``ubus call wifi status`` (available on OpenWrt with a recent wpad /
hostapd). Reports each radio's operating parameters and the currently
associated station clients.
"""

from __future__ import annotations

import re

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import WifiClient, WifiInfo, WifiRadio

_WIDTH = re.compile(r"(20|40|80|160|320)")

_KNOWN_WIDTHS = {20: 20, 40: 40, 80: 80, 160: 160, 320: 320}


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


class WifiCollector(Collector):
    name = "wifi"

    def collect(self, ctx: CollectorContext) -> WifiInfo:
        try:
            status = ctx.ubus.call("wifi", "status")
        except Exception:  # noqa: BLE001
            return WifiInfo()

        radios: list[WifiRadio] = []
        clients: list[WifiClient] = []
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

            hwmode = config.get("hwmode")
            htmode = config.get("htmode")
            frequency = None
            freq = config.get("frequency")
            if freq:
                try:
                    frequency = int(freq)
                except (TypeError, ValueError):
                    frequency = None

            channel = config.get("channel")
            tx_power = config.get("txpower")
            stations = radio.get("stations") or {}
            station_count = len(stations) if isinstance(stations, dict) else 0

            radios.append(
                WifiRadio(
                    name=radio_name,
                    up=bool(radio.get("up", False)),
                    mode=config.get("mode"),
                    band=_band(hwmode, frequency),
                    channel=int(channel) if channel else None,
                    frequency_mhz=frequency,
                    tx_power=int(tx_power) if tx_power else None,
                    ssid=ssid,
                    hwmode=hwmode,
                    width_mhz=_width_mhz(htmode, hwmode),
                    station_count=station_count,
                )
            )
            for mac, station in (stations or {}).items():
                if not isinstance(station, dict):
                    continue
                signal = station.get("signal")
                clients.append(
                    WifiClient(
                        mac=mac,
                        ssid=ssid,
                        signal_dbm=int(signal) if signal is not None else None,
                        tx_bytes=int(station.get("txbytes") or 0) or None,
                        rx_bytes=int(station.get("rxbytes") or 0) or None,
                        connected_minutes=int(station.get("connected_time") or 0) or None,
                    )
                )
        return WifiInfo(radios=radios, clients=clients)
