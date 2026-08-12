"""Client connection-medium classification.

Derives each client's connection type (``wired`` / ``wireless`` / ``unknown``)
from actual OpenWrt runtime data instead of guessing from interface names
alone. OpenWrt bridges its physical LAN ports and AP interfaces into one bridge
(``br-lan``), so a lease/ARP/ND entry that names only ``lan`` or ``br-lan`` is
ambiguous: the same bridge carries wired and wireless traffic. The reliable
signals, in order:

1. an associated WiFi station (``iw``/``ubus`` station data) is wireless;
2. the interface the client is seen on is a live wireless interface (the wifi
   collector discovers these from sysfs ``phy80211``/``wireless`` entries);
3. the interface is a bridge — classify its members: all-wireless bridge is
   wireless, all-wired bridge is wired, anything else is unknown;
4. a clearly named wired link (``eth*``, ``lan<port>``, ``wan``, ppp...) is wired;
5. everything else stays ``unknown`` — nothing is falsely classified.

The result maps a normalized MAC (lowercase, no separators) to its medium. Only
MACs seen in leases, ARP, IPv6 neighbors or the station list are included.
"""

from __future__ import annotations

import re

from router_agent.model import (
    ArpEntry,
    DhcpLease,
    NeighborEntry,
    NetworkInterface,
    WifiClient,
)

WIRED = "wired"
WIRELESS = "wireless"
UNKNOWN = "unknown"

#: Wireless interface names across OpenWrt naming schemes: mac80211 (``phy0-ap0``,
#: ``wlan0``), Broadcom/brcmfmac (``wl0``), Ralink/MediaTek (``ra0``/``rai0``),
#: older drivers (``radio0``, ``wifi0``). Everything here is *also* discovered by
#: the wifi collector from sysfs; the pattern is a fallback for callers that do
#: not carry the live wireless set.
_WIRELESS_IFACE = re.compile(r"^(phy|wlan|wl|wifi|radio|ra|rai)[0-9a-z\-]*$", re.I)

#: Wired physical/uplink interfaces. ``lan<port>``/``eth*`` are LAN switch ports,
#: ``wan``/ppp/wwan/usb* are uplinks. A bare logical ``lan`` is deliberately NOT
#: matched — it is a bridge and handled by the bridge-member logic.
_WIRED_IFACE = re.compile(
    r"^(eth|en|ge|gbe|xgbe|wan[0-9]?|lan[0-9]|usb|ppp|wwan)[0-9a-z.\-]*$", re.I
)


def normalize_mac(mac: str | None) -> str | None:
    """Normalize a MAC to ``aabbccddeeff`` (lowercase, no separators)."""
    if not mac:
        return None
    compact = mac.lower().replace(":", "").replace("-", "").replace(".", "")
    return compact if re.fullmatch(r"[0-9a-f]{12}", compact) else None


def _bridge_members_of(network: list[NetworkInterface]) -> dict[str, set[str]]:
    """Map every interface name/device that is a bridge to its member set."""
    members: dict[str, set[str]] = {}
    for iface in network:
        if not iface.is_bridge and not (iface.name or "").startswith("br-"):
            continue
        member_set = {m for m in (iface.bridge_members or []) if m}
        if not member_set:
            continue
        if iface.name:
            members.setdefault(iface.name, set()).update(member_set)
        if iface.device and iface.device != iface.name:
            members.setdefault(iface.device, set()).update(member_set)
    return members


def _logical_device_map(network: list[NetworkInterface]) -> dict[str, str]:
    """Map logical interface names (``lan``) to their device (``br-lan``)."""
    return {iface.name: iface.device for iface in network if iface.name and iface.device}


def _member_medium(
    member: str,
    wireless_interfaces: set[str],
) -> str:
    if member in wireless_interfaces or _WIRELESS_IFACE.match(member):
        return WIRELESS
    if _WIRED_IFACE.match(member):
        return WIRED
    return UNKNOWN


def _iface_medium(
    iface: str,
    wireless_interfaces: set[str],
    bridge_members: dict[str, set[str]],
    logical_devices: dict[str, str],
) -> str:
    if iface in wireless_interfaces:
        return WIRELESS
    if _WIRELESS_IFACE.match(iface):
        return WIRELESS
    if _WIRED_IFACE.match(iface):
        return WIRED
    resolved = logical_devices.get(iface, iface)
    members = bridge_members.get(resolved) or bridge_members.get(iface)
    if members:
        media = {_member_medium(m, wireless_interfaces) for m in members}
        if media == {WIRELESS}:
            return WIRELESS
        if media == {WIRED}:
            return WIRED
        return UNKNOWN
    return UNKNOWN


def classify_client_media(
    *,
    leases: list[DhcpLease] | None = None,
    arp: list[ArpEntry] | None = None,
    neighbors: list[NeighborEntry] | None = None,
    wifi_clients: list[WifiClient] | None = None,
    network: list[NetworkInterface] | None = None,
    wireless_interfaces: set[str] | list[str] | frozenset[str] | None = None,
) -> dict[str, str]:
    """Map every known client MAC to ``wired``/``wireless``/``unknown``.

    Station MACs are always wireless. Other MACs are classified from the union
    of the interfaces they were seen on; any wireless signal wins, otherwise
    the sources must agree on wired before a wired verdict is given.
    """
    wifi_clients = wifi_clients or []
    wireless_ifaces = set(wireless_interfaces or ())
    wireless_ifaces.update(c.interface for c in wifi_clients if c.interface)
    station_macs = {normalize_mac(c.mac) for c in wifi_clients}
    station_macs.discard(None)

    bridge_members = _bridge_members_of(network or [])
    logical_devices = _logical_device_map(network or [])

    ifaces_by_mac: dict[str, set[str]] = {}
    for lease in leases or []:
        if lease.mac and lease.interface:
            key = normalize_mac(lease.mac)
            if key:
                ifaces_by_mac.setdefault(key, set()).add(lease.interface)
    for entry in arp or []:
        if entry.mac and entry.interface:
            key = normalize_mac(entry.mac)
            if key:
                ifaces_by_mac.setdefault(key, set()).add(entry.interface)
    for entry in neighbors or []:
        if entry.mac and entry.interface:
            key = normalize_mac(entry.mac)
            if key:
                ifaces_by_mac.setdefault(key, set()).add(entry.interface)

    result: dict[str, str] = {}
    for mac in station_macs:
        result[mac] = WIRELESS

    for mac, interfaces in ifaces_by_mac.items():
        if mac in result:
            continue
        media = {
            _iface_medium(i, wireless_ifaces, bridge_members, logical_devices) for i in interfaces
        }
        if WIRELESS in media:
            result[mac] = WIRELESS
        elif media == {WIRED}:
            result[mac] = WIRED
        else:
            result[mac] = UNKNOWN
    return result


__all__ = ["classify_client_media", "normalize_mac"]
