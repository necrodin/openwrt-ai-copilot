"""WiFi collector.

Combines the live ``ubus call wifi status`` view (radio operating state and
associated stations) with the configured UCI wireless tree (``uci show
wireless``), so the snapshot carries both the *configured* SSIDs — including
disabled ones — and the *live* radios and station metrics.

``ubus call wifi status`` is not available on every OpenWrt build (the object
may be absent and the call fails with ``UBUS_STATUS_NOT_FOUND``). When that
happens the collector falls back to the configured ``wifi-device`` sections and
the live kernel wireless interfaces (``/sys/class/net/*`` with a
``wireless``/``phy80211`` entry) so radios are still identified from the device
state that *is* available. Radio presence never comes from ``uci`` alone: a
configured device without a live interface is reported as a (down) radio only
when the device itself is configured; nothing is invented.
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

#: One-shot live wireless interface enumeration. Discovers every kernel network
#: interface backed by a wireless phy — a ``wireless`` sysfs directory (legacy
#: drivers) or a ``phy80211`` symlink (modern mac80211, e.g. ``phy0-ap0`` on
#: ath79) — which is what distinguishes radios/APs from wired links on every
#: OpenWrt naming scheme. Emits ``ifname|phy|carrier|flags|stations|device``
#: where ``device`` is the resolved sysfs device path (used to match live
#: interfaces back to UCI ``wifi-device`` sections that carry a ``path``).
_LIVE_WIRELESS_CMD = (
    "for i in /sys/class/net/*; do "
    "n=${i##*/}; "
    "[ -d /sys/class/net/$n/wireless ] || [ -e /sys/class/net/$n/phy80211 ] || continue; "
    "p=$(basename $(readlink -f /sys/class/net/$n/phy80211) 2>/dev/null); "
    "c=$(cat /sys/class/net/$n/carrier 2>/dev/null); "
    "f=$(cat /sys/class/net/$n/flags 2>/dev/null); "
    "s=$(iw dev $n station dump 2>/dev/null | grep -c '^Station '); "
    "d=$(readlink -f /sys/class/net/$n/device 2>/dev/null); "
    "echo \"$n|${p:-}|${c:-0}|${f:-0}|${s:-0}|${d:-}\"; "
    "done"
)


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


def _band_from_uci(band: str | None) -> str | None:
    """Map the modern UCI ``band`` option (``5g``/``2g``/``6g``) to a label."""
    if not band:
        return None
    value = band.lower().replace("ghz", "")
    if value in ("5g", "5ghz", "a", "ac", "ax"):
        return "5GHz"
    if value in ("2g", "2.4g", "2.4ghz", "b", "g", "n"):
        return "2.4GHz"
    if value in ("6g", "6ghz"):
        return "6GHz"
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
    """Parse ``uci show wireless`` into (device configs, wifi-iface configs).

    Devices are keyed by their UCI section key (``radio0``) and retain their
    ``name`` (the phy name, e.g. ``phy0``) inside the section so consumers can
    match live interfaces regardless of naming scheme.
    """
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
            devices[key] = section
        elif stype == "wifi-iface":
            ifaces.append({**section, "_section": key})
    return devices, ifaces


def _live_wireless_ifaces(ctx: CollectorContext) -> dict[str, dict[str, Any]]:
    """Discover live wireless interfaces from ``/sys/class/net``.

    Returns ``{ifname: {"phy", "up", "stations"}}``. ``up`` is derived from the
    interface flags (IFF_UP) or carrier, which works for AP interfaces even
    while no station is associated. Absent ``iw`` (or a read-only fs) yields an
    empty result without raising.
    """
    result: dict[str, dict[str, Any]] = {}
    for line in ctx.sh(_LIVE_WIRELESS_CMD, default="").splitlines():
        parts = line.split("|")
        if len(parts) < 5:
            continue
        name, phy, carrier, flags, count = parts[:5]
        device = parts[5] if len(parts) > 5 else None
        if not name:
            continue
        up = False
        try:
            up = bool(int(flags, 16) & 0x1)
        except ValueError:
            up = carrier == "1"
        result[name] = {
            "phy": phy,
            "up": up or carrier == "1",
            "stations": int(count) if count.isdigit() else 0,
            "device": device or None,
        }
    return result


def _count_iface_stations(ctx: CollectorContext, ifname: str) -> int:
    """Number of associated stations on one interface via ``iw``."""
    output = ctx.sh(f"iw dev {ifname} station dump 2>/dev/null", default="")
    return sum(1 for line in output.splitlines() if _STATION_LINE.match(line.strip()))


def _radio_device(devices: dict[str, dict], name: str) -> dict:
    """Resolve a UCI device section by section key or by its ``name``/phy."""
    if name in devices:
        return devices[name]
    return next((d for d in devices.values() if d.get("name") == name), {})


def _device_phy_name(device: dict, section_key: str) -> str | None:
    """The phy name a UCI ``wifi-device`` section binds to, if known."""
    return device.get("name") or None


def _paths_match(device_path: str | None, uci_path: str | None) -> bool:
    """True when a live sysfs device path and a UCI ``path`` describe one device.

    UCI ``path`` values are relative to ``/sys/devices`` (e.g.
    ``platform/ahb/18100000.wmac`` or ``pci0000:00/0000:00:00.0``) while the
    live ``device`` resolved from ``/sys/class/net/`` is absolute (``/sys/
    devices/...``). Normalize the UCI path to its absolute form and compare.
    """
    if not device_path or not uci_path:
        return False
    if not uci_path.startswith("/"):
        uci_path = f"/sys/devices/{uci_path}"
    return device_path.rstrip("/") == uci_path.rstrip("/")


def _matching_live_ifaces(
    live: dict[str, dict[str, Any]],
    device: dict,
    section_key: str,
    ifaces: list[dict],
) -> list[tuple[str, dict[str, Any]]]:
    """Live interfaces that belong to one UCI ``wifi-device`` section.

    Matches by the device's phy ``name`` (modern OpenWrt ``phy0``), a legacy
    ``ifname`` on its ``wifi-iface`` sections, or the device ``path`` resolved
    from sysfs (ath79/mac80211 where the phy name is not in UCI). Handles any
    interface naming scheme.
    """
    matched: list[tuple[str, dict[str, Any]]] = []
    seen: set[str] = set()

    phy = _device_phy_name(device, section_key)
    uci_path = device.get("path")
    legacy_ifnames = {
        iface.get("ifname")
        for iface in ifaces
        if iface.get("device") == section_key and iface.get("ifname")
    }

    for ifname, info in live.items():
        if info.get("phy") and phy and info["phy"] == phy:
            matched.append((ifname, info))
            seen.add(ifname)
            continue
        if ifname in legacy_ifnames:
            matched.append((ifname, info))
            seen.add(ifname)
            continue
        if _paths_match(info.get("device"), uci_path):
            matched.append((ifname, info))
            seen.add(ifname)
    return matched


class WifiCollector(Collector):
    name = "wifi"

    def collect(self, ctx: CollectorContext) -> WifiInfo:
        try:
            status = ctx.ubus.call("wifi", "status")
        except Exception:  # noqa: BLE001 - best-effort; fall back to UCI/live
            status = {}

        devices, ifaces = _parse_uci_wireless(ctx.sh("uci show wireless", default=""))
        live = _live_wireless_ifaces(ctx)

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
        emitted_radios: set[str] = set()

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

            uci_device = _radio_device(devices, radio_name)
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
            emitted_radios.add(radio_name)

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

        # Fallback: when the live ubus view is unavailable, identify radios from
        # the configured wifi-device sections and the live kernel interfaces.
        if not status:
            radios.extend(
                self._radios_from_uci(ctx, devices, ifaces, live, emitted_radios)
            )

        for iface in ifaces:
            ssid = iface.get("ssid", "")
            device = iface.get("device", "")
            ifname = live_ifaces.get((device, ssid))
            client_count = 0
            if ifname and device and ssid:
                counted.add((device, ssid))
                client_count = _count_iface_stations(ctx, ifname)
            elif not status:
                # Without ubus, fall back to the live iface(s) of the device so
                # configured SSIDs still report their station counts.
                uci_device = _radio_device(devices, device)
                matched = _matching_live_ifaces(live, uci_device, device, ifaces)
                stations_total = sum(info["stations"] for _, info in matched)
                if len(matched) == 1 and stations_total:
                    ifname = matched[0][0]
                    client_count = stations_total
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

    @staticmethod
    def _radios_from_uci(
        ctx: CollectorContext,
        devices: dict[str, dict],
        ifaces: list[dict],
        live: dict[str, dict[str, Any]],
        emitted: set[str],
    ) -> list[WifiRadio]:
        """Build radios from configured ``wifi-device`` sections + live ifaces.

        A configured device is always reported (it is real, even when currently
        down/disabled); its ``up``/``station_count`` come only from live kernel
        state. Live wireless interfaces whose phy belongs to no configured
        device are surfaced as radios too (e.g. radios managed outside UCI), so
        genuinely present hardware is never missed.
        """
        result: list[WifiRadio] = []
        claimed_phys: set[str] = set()

        for section_key, device in devices.items():
            if section_key in emitted:
                continue
            matched = _matching_live_ifaces(live, device, section_key, ifaces)
            up = any(info["up"] for _, info in matched)
            stations = sum(info["stations"] for _, info in matched)

            ssid = next(
                (i.get("ssid") for i in ifaces if i.get("device") == section_key and i.get("ssid")),
                None,
            )
            hwmode = device.get("hwmode")
            band = _band(hwmode, None) or _band_from_uci(device.get("band"))
            if up and matched:
                phy = matched[0][1].get("phy")
                if phy:
                    claimed_phys.add(phy)

            result.append(
                WifiRadio(
                    name=section_key,
                    up=up,
                    mode=None,
                    band=band,
                    channel=_as_int(device.get("channel")),
                    frequency_mhz=None,
                    tx_power=_as_int(device.get("txpower")),
                    ssid=ssid,
                    hwmode=hwmode,
                    width_mhz=_width_mhz(device.get("htmode"), hwmode),
                    station_count=stations,
                    country=device.get("country"),
                    hardware=device.get("path"),
                )
            )

        # Live radios with no UCI wifi-device section (unmanaged/adhoc) still
        # count as real radios.
        for ifname, info in live.items():
            phy = info.get("phy")
            if not phy or phy in claimed_phys:
                continue
            name = phy or ifname
            if name in emitted:
                continue
            claimed_phys.add(phy)
            result.append(
                WifiRadio(
                    name=name,
                    up=info["up"],
                    station_count=info["stations"],
                    ssid=None,
                )
            )
        return result
