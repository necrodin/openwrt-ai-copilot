"""WiFi collector.

Source: ``ubus call wifi status`` (available on OpenWrt with a recent wpad /
hostapd). Reports each radio's operating parameters and the currently
associated station clients.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import WifiClient, WifiInfo, WifiRadio


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
