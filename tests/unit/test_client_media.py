"""Regression tests for client connection-medium classification.

Real-device bug: on the AC2350 (and any OpenWrt build without the ``ubus wifi
status`` object) every client on the bridged LAN was labelled ``wired`` because
classification used interface names alone (``lan``/``br-lan`` match nothing).
These tests pin the corrected behaviour: medium comes from actual runtime data
— associated WiFi stations, live wireless interfaces, and bridge member
topology — and ambiguous clients stay ``unknown`` instead of being guessed.
"""

from __future__ import annotations

import json

from router_agent.client_media import classify_client_media, normalize_mac
from router_agent.collectors.arp import ArpCollector
from router_agent.collectors.clients import ClientsCollector
from router_agent.collectors.neighbors import NeighborsCollector
from router_agent.collectors.network import NetworkCollector
from router_agent.collectors.wifi import WifiCollector
from router_agent.model import ArpEntry, DhcpLease, NetworkInterface, WifiClient
from router_agent.snapshot import build_snapshot
from tests.unit.router_agent_helpers import make_context

_DNS_CMD = (
    "cat /etc/resolv.conf 2>/dev/null; "
    "cat /tmp/resolv.conf.d/*.auto /tmp/resolv.conf.d/*.conf 2>/dev/null"
)

_MIXED_BRIDGE = NetworkInterface(
    name="lan",
    up=True,
    proto="static",
    device="br-lan",
    is_bridge=True,
    bridge_members=["lan1", "lan2", "lan3", "lan4", "phy0-ap0", "phy1-ap0"],
)
_WIRED_BRIDGE = NetworkInterface(
    name="lan",
    up=True,
    proto="static",
    device="br-lan",
    is_bridge=True,
    bridge_members=["lan1", "lan2", "lan3", "lan4"],
)
_WIFI_BRIDGE = NetworkInterface(
    name="lan",
    up=True,
    proto="static",
    device="br-lan",
    is_bridge=True,
    bridge_members=["phy0-ap0", "phy1-ap0"],
)


def _lease(mac: str, interface: str = "lan") -> DhcpLease:
    return DhcpLease(hostname="device", ip="192.168.1.50", mac=mac, interface=interface)


def _arp(mac: str, interface: str = "br-lan") -> ArpEntry:
    return ArpEntry(ip="192.168.1.50", mac=mac, interface=interface, state="REACHABLE")


def _station(mac: str, interface: str = "phy0-ap0") -> WifiClient:
    return WifiClient(mac=mac, interface=interface, ssid="Xiaomi_5G", signal_dbm=-60)


def test_normalize_mac() -> None:
    assert normalize_mac("AA:BB:CC:00:00:01") == "aabbcc000001"
    assert normalize_mac("aa-bb-cc-dd-ee-ff") == "aabbccddeeff"
    assert normalize_mac(None) is None
    assert normalize_mac("not-a-mac") is None


def test_wireless_station_recognized_as_wireless() -> None:
    """A client that is an associated WiFi station is wireless, no matter what
    interface its lease/ARP entry names (a bridged ``lan``)."""
    leases = [_lease("aa:bb:cc:00:00:01")]
    arp = [_arp("aa:bb:cc:00:00:01")]
    result = classify_client_media(
        leases=leases,
        arp=arp,
        wifi_clients=[_station("aa:bb:cc:00:00:01")],
        network=[_MIXED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    assert result["aabbcc000001"] == "wireless"


def test_wired_lan_client_recognized_as_wired() -> None:
    """A client on a wired-only bridge (or a direct wired interface) is wired."""
    result = classify_client_media(
        leases=[_lease("aa:aa:aa:aa:aa:aa")],
        network=[_WIRED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    assert result["aaaaaaaaaaaa"] == "wired"

    result = classify_client_media(
        leases=[_lease("bb:bb:bb:bb:bb:bb", interface="eth0.1")],
        network=[],
        wireless_interfaces=[],
    )
    assert result["bbbbbbbbbbbb"] == "wired"


def test_bridge_client_correctly_classified() -> None:
    """Bridge members decide the medium: all-wireless bridge -> wireless,
    all-wired bridge -> wired."""
    wireless = classify_client_media(
        leases=[_lease("aa:bb:cc:00:00:01")],
        network=[_WIFI_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    assert wireless["aabbcc000001"] == "wireless"

    wired = classify_client_media(
        leases=[_lease("aa:aa:aa:aa:aa:aa")],
        network=[_WIRED_BRIDGE],
        wireless_interfaces=[],
    )
    assert wired["aaaaaaaaaaaa"] == "wired"


def test_ambiguous_client_remains_unknown() -> None:
    """A client on a bridge that carries BOTH wired and wireless traffic, and is
    not an associated station, is genuinely ambiguous -> unknown, never wired."""
    result = classify_client_media(
        leases=[_lease("22:22:22:22:22:22"), _lease("33:33:33:33:33:33")],
        arp=[_arp("33:33:33:33:33:33")],
        wifi_clients=[],
        network=[_MIXED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    assert result["222222222222"] == "unknown"
    assert result["333333333333"] == "unknown"

    # No bridge topology at all -> unknown, not a guessed "wired".
    no_topology = classify_client_media(
        leases=[_lease("44:44:44:44:44:44")],
        network=[],
        wireless_interfaces=[],
    )
    assert no_topology["444444444444"] == "unknown"


def test_offline_wireless_client_remains_wireless() -> None:
    """A wireless client that was an associated station keeps its wireless
    classification (the frontend carry-forward preserves it across polls)."""
    result = classify_client_media(
        leases=[_lease("aa:bb:cc:00:00:01")],
        wifi_clients=[_station("aa:bb:cc:00:00:01")],
        network=[_MIXED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    assert result["aabbcc000001"] == "wireless"

    # A station seen ONLY in the station list (no lease/ARP yet) is wireless too.
    station_only = classify_client_media(
        wifi_clients=[_station("ee:ee:ee:ee:ee:ee")],
        network=[_MIXED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    assert station_only["eeeeeeeeeeee"] == "wireless"


def test_client_media_supports_wireless_filter() -> None:
    """The medium values are exactly what the UI filter consumes: station MACs
    are ``wireless``, mixed-bridge clients are not wireless (so they do not
    leak into the Wireless filter)."""
    station = _station("aa:bb:cc:00:00:01")
    ambiguous = _lease("55:55:55:55:55:55")
    result = classify_client_media(
        leases=[_lease("aa:bb:cc:00:00:01"), ambiguous],
        arp=[_arp("aa:bb:cc:00:00:01")],
        wifi_clients=[station],
        network=[_MIXED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )
    wireless = {mac for mac, medium in result.items() if medium == "wireless"}
    assert wireless == {"aabbcc000001"}
    assert "555555555555" not in wireless


def test_existing_client_totals_remain_correct() -> None:
    """Every lease MAC keeps an entry; the medium map never drops or invents
    clients, and the wireless count matches the real station set."""
    station_macs = [f"aa:bb:cc:00:00:{i:02x}" for i in range(1, 6)]
    other_macs = [f"aa:bb:cc:00:01:{i:02x}" for i in range(1, 20)]
    leases = [_lease(mac, interface="lan") for mac in [*station_macs, *other_macs]]
    arp = [_arp(mac) for mac in station_macs]
    wifi_clients = [_station(mac) for mac in station_macs]

    result = classify_client_media(
        leases=leases,
        arp=arp,
        wifi_clients=wifi_clients,
        network=[_MIXED_BRIDGE],
        wireless_interfaces=["phy0-ap0", "phy1-ap0"],
    )

    assert len(result) == len(leases)
    assert set(result) == {normalize_mac(m) for m in [*station_macs, *other_macs]}
    wireless = {mac for mac, medium in result.items() if medium == "wireless"}
    assert wireless == {normalize_mac(m) for m in station_macs}
    assert sum(1 for medium in result.values() if medium == "wired") == 0


def test_snapshot_assembles_client_media_from_ac2350_shape() -> None:
    """End-to-end: the snapshot assembler computes ``client_media`` from the
    AC2350-shaped collectors (no ``ubus wifi status`` object). 5 associated
    stations on a mixed LAN bridge are wireless; the rest of the leases are
    unknown."""
    lease_macs = [f"aa:bb:cc:00:00:{i:02x}" for i in range(1, 6)]
    other_macs = [f"aa:bb:cc:00:01:{i:02x}" for i in range(1, 20)]
    leases = [
        {
            "hostname": f"d{i}",
            "ip": f"192.168.1.{100 + i}",
            "mac": mac,
            "expires": "123",
            "interface": "lan",
        }
        for i, mac in enumerate([*lease_macs, *other_macs], start=1)
    ]
    arp_lines = ["IP address       HW type     Flags       HW address            Mask     Device"]
    arp_lines += [
        f"192.168.1.{100 + i}     0x1         0x2         {mac}     *        br-lan"
        for i, mac in enumerate(lease_macs, start=1)
    ]
    wifi_uci = (
        "wireless=wireless\n"
        "wireless.radio0=wifi-device\nwireless.radio0.name='phy0'\nwireless.radio0.type='mac80211'\n"
        "wireless.radio0.path='1e140000.pcie'\n"
        "wireless.radio0.ssid0=wifi-iface\nwireless.radio0.ssid0.device='radio0'\n"
        "wireless.radio0.ssid0.mode='ap'\nwireless.radio0.ssid0.ssid='Xiaomi_5G'\n"
        "wireless.radio1=wifi-device\nwireless.radio1.name='phy1'\nwireless.radio1.type='mac80211'\n"
        "wireless.radio1.path='1e140000.pcie1'\n"
        "wireless.radio1.ssid1=wifi-iface\nwireless.radio1.ssid1.device='radio1'\n"
        "wireless.radio1.ssid1.mode='ap'\nwireless.radio1.ssid1.ssid='Xiaomi_2G'\n"
    )
    station_dump_5g = "".join(
        f"Station {mac} (on phy0-ap0)\n\tsignal:  -60 dBm\n\ttx bytes: 100\n\trx bytes: 200\n"
        for mac in lease_macs[:3]
    )
    station_dump_2g = "".join(
        f"Station {mac} (on phy1-ap0)\n\tsignal:  -55 dBm\n" for mac in lease_macs[3:]
    )

    ctx = make_context(
        {
            "ubus call dhcp leases": json.dumps({"leases": leases}),
            "cat /proc/net/arp": "\n".join(arp_lines),
            "ip -6 neigh show": "",
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {"interface": "lan", "up": True, "proto": "static", "device": "br-lan"},
                        {"interface": "wan", "up": True, "proto": "dhcp", "device": "eth0"},
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(
                {
                    "br-lan": {
                        "up": True,
                        "type": "bridge",
                        "ports": [
                            {"ifname": "lan1"},
                            {"ifname": "lan2"},
                            {"ifname": "lan3"},
                            {"ifname": "lan4"},
                            {"ifname": "phy0-ap0"},
                            {"ifname": "phy1-ap0"},
                        ],
                        "statistics": {},
                    }
                }
            ),
            "ip -o route show default": "default via 192.168.31.1 dev eth0",
            _DNS_CMD: "",
            "uci show wireless": wifi_uci,
            "for i in /sys/class/net/*; do": (
                "phy0-ap0|phy0|1|0x1003|3|/sys/devices/1e140000.pcie\n"
                "phy1-ap0|phy1|1|0x1003|2|/sys/devices/1e140000.pcie1\n"
            ),
            "iw dev phy0-ap0 station dump 2>/dev/null": station_dump_5g,
            "iw dev phy1-ap0 station dump 2>/dev/null": station_dump_2g,
        }
    )

    snapshot = build_snapshot(
        ctx,
        [
            NetworkCollector(),
            WifiCollector(),
            ClientsCollector(),
            ArpCollector(),
            NeighborsCollector(),
        ],
        device_id="ac2350",
        transport="ssh",
        host="192.168.31.1",
    )

    assert len(snapshot.clients) == 24
    assert len(snapshot.wifi.clients) == 5
    assert set(ctx.state["wireless_interfaces"]) == {"phy0-ap0", "phy1-ap0"}
    assert len(snapshot.client_media) == 24
    wireless = {mac for mac, medium in snapshot.client_media.items() if medium == "wireless"}
    assert wireless == {normalize_mac(mac) for mac in lease_macs}
    assert snapshot.client_media[normalize_mac("aa:bb:cc:00:00:01")] == "wireless"
    assert snapshot.client_media[normalize_mac(other_macs[0])] == "unknown"
