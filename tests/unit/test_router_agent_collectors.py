"""Collector unit tests using a scripted command runner."""

from __future__ import annotations

import json

from router_agent.collectors.arp import ArpCollector
from router_agent.collectors.clients import ClientsCollector
from router_agent.collectors.cpu import CpuCollector
from router_agent.collectors.dhcp import DhcpCollector
from router_agent.collectors.firewall import FirewallCollector
from router_agent.collectors.kernel import KernelCollector
from router_agent.collectors.logs import LogsCollector
from router_agent.collectors.memory import MemoryCollector
from router_agent.collectors.neighbors import NeighborsCollector
from router_agent.collectors.network import NetworkCollector
from router_agent.collectors.packages import PackagesCollector
from router_agent.collectors.routing import RoutingCollector
from router_agent.collectors.services import ServicesCollector
from router_agent.collectors.storage import StorageCollector
from router_agent.collectors.temperature import TemperatureCollector
from router_agent.collectors.vpn import VpnCollector
from router_agent.collectors.wifi import WifiCollector
from tests.unit.router_agent_helpers import make_context


def test_cpu_collector() -> None:
    ctx = make_context(
        {
            "ubus call system info": json.dumps(
                {"load_1": 0.5, "load_5": 0.4, "load_15": 0.3, "uptime": 120}
            ),
            "cat /proc/cpuinfo": "processor : 0\nprocessor : 1\nprocessor : 2\n",
        }
    )
    cpu = CpuCollector().collect(ctx)
    assert cpu.load_1 == 0.5
    assert cpu.load_15 == 0.3
    assert cpu.cores == 3
    assert cpu.uptime_seconds == 120.0


def test_cpu_collector_falls_back_to_loadavg() -> None:
    ctx = make_context({"cat /proc/loadavg": "0.11 0.09 0.06 1/2 123"})
    cpu = CpuCollector().collect(ctx)
    assert cpu.load_1 == 0.11
    assert cpu.cores == 1


def test_cpu_collector_load_fixed_point_array() -> None:
    """OpenWrt ``ubus system info`` returns load as a fixed-point array (1/65536)."""
    ctx = make_context(
        {
            "ubus call system info": json.dumps(
                {"load": [32512, 65536, 98304], "uptime": 150773}
            ),
            "cat /proc/cpuinfo": "processor\t\t: 0\n",
        }
    )
    cpu = CpuCollector().collect(ctx)
    assert cpu.load_1 == round(32512 / 65536, 2)
    assert cpu.load_5 == 1.0
    assert cpu.load_15 == round(98304 / 65536, 2)
    assert cpu.uptime_seconds == 150773.0


def test_cpu_collector_mips_cpuinfo_model() -> None:
    """MIPS firmware lacks ``model name``; fall back to ``cpu model``/``system type``."""
    ctx = make_context(
        {
            "ubus call system info": json.dumps({"load": [65536, 32768, 16384]}),
            "cat /proc/cpuinfo": (
                "system type\t\t: Qualcomm Atheros QCA956X ver 1 rev 0\n"
                "machine\t\t\t: Xiaomi AIoT AC2350\n"
                "processor\t\t: 0\n"
                "cpu model\t\t: MIPS 74Kc V5.0\n"
            ),
        }
    )
    cpu = CpuCollector().collect(ctx)
    assert cpu.cores == 1
    assert cpu.model == "MIPS 74Kc V5.0"
    assert cpu.load_1 == 1.0
    assert cpu.architecture is None


def test_cpu_collector_load_fallback_from_loadavg() -> None:
    """A load array that is truncated fill from /proc/loadavg without inventing NaN."""
    ctx = make_context(
        {
            "ubus call system info": json.dumps({"load": [32768], "uptime": 99}),
            "cat /proc/loadavg": "0.44 0.33 0.22 1/2 123",
            "cat /proc/cpuinfo": "processor : 0\n",
        }
    )
    cpu = CpuCollector().collect(ctx)
    assert cpu.load_1 == 0.5
    assert cpu.load_5 == 0.33
    assert cpu.load_15 == 0.22


def test_cpu_collector_missing_fields_do_not_crash() -> None:
    """Empty/malformed ubus output produces zeros/null, never an exception."""
    ctx = make_context(
        {
            "ubus call system info": json.dumps({"load": "not-a-list"}),
            "cat /proc/cpuinfo": "processor : 0\n",
        }
    )
    cpu = CpuCollector().collect(ctx)
    assert cpu.load_1 == 0.0
    assert cpu.load_5 == 0.0
    assert cpu.load_15 == 0.0
    assert cpu.cores == 1
    assert cpu.model is None
    assert cpu.usage_percent is None


def test_cpu_collector_usage_from_proc_stat() -> None:
    """CPU utilization derives from a /proc/stat delta, not load average."""
    ctx = make_context(
        {
            "head -n1 /proc/stat; sleep 1 2>/dev/null || sleep 0; head -n1 /proc/stat": (
                "cpu  1000 0 1000 8000 0 0 0 0 0 0\n"
                "cpu  2000 0 2000 8800 0 0 0 0 0 0\n"
            )
        }
    )
    cpu = CpuCollector().collect(ctx)
    total_before = 1000 + 1000 + 8000
    total_after = 2000 + 2000 + 8800
    idle_before = 8000
    idle_after = 8800
    busy = 1.0 - (idle_after - idle_before) / (total_after - total_before)
    expected = round(min(100.0, max(0.0, busy) * 100), 1)
    assert cpu.usage_percent == expected


def test_memory_collector_from_proc() -> None:
    ctx = make_context(
        {
            "cat /proc/meminfo": (
                "MemTotal:       500000 kB\n"
                "MemFree:        100000 kB\n"
                "Buffers:         20000 kB\n"
                "Cached:          30000 kB\n"
                "MemAvailable:   150000 kB\n"
            )
        }
    )
    memory = MemoryCollector().collect(ctx)
    assert memory.total_kb == 500000
    assert memory.free_kb == 100000
    assert memory.buffered_kb == 20000
    assert memory.cached_kb == 30000
    assert memory.available_kb == 150000
    assert memory.used_kb == 350000


def test_memory_collector_falls_back_to_ubus() -> None:
    ctx = make_context(
        {
            "ubus call system info": json.dumps(
                {"memory": {"total": 512000, "free": 256000, "buffered": 8000}}
            )
        }
    )
    memory = MemoryCollector().collect(ctx)
    assert memory.total_kb == 512000
    assert memory.used_kb == 256000


def test_temperature_collector() -> None:
    ctx = make_context(
        {
            "ls /sys/class/thermal/": "cooling_device0 thermal_zone0\n",
            "cat /sys/class/thermal/thermal_zone0/temp": "52000",
            "cat /sys/class/thermal/thermal_zone0/type": "cpu-thermal",
        }
    )
    readings = TemperatureCollector().collect(ctx)
    assert [r.model_dump() for r in readings] == [{"zone": "cpu-thermal", "temperature_c": 52.0}]


def test_temperature_collector_empty() -> None:
    ctx = make_context({"ls /sys/class/thermal/": "cooling_device0\n"})
    assert TemperatureCollector().collect(ctx) == []


def test_storage_collector() -> None:
    ctx = make_context(
        {
            "df -kPT": (
                "Filesystem     Type  1024-blocks    Used  Available Capacity Mounted on\n"
                "ubi0:rootfs    ubifs      65536   30000      35000      47% /\n"
                "/dev/sda1      ext4     1000000  200000    800000      21% /overlay\n"
            ),
            "df -i": (
                "Filesystem      Inodes IUsed IFree IUse% Mounted on\n"
                "ubi0:rootfs      65536 30000 35536    46% /\n"
                "/dev/sda1       262144 20000 242144     8% /overlay\n"
            ),
        }
    )
    mounts = StorageCollector().collect(ctx)
    assert len(mounts) == 2
    root = mounts[0]
    assert root.mountpoint == "/"
    assert root.filesystem == "ubifs"
    assert root.total_bytes == 65536 * 1024
    assert root.use_percent == 47.0
    assert root.inode_use_percent == 46.0
    assert root.inodes_used == 30000
    assert root.health == "ok"
    assert mounts[1].mountpoint == "/overlay"
    assert mounts[1].filesystem == "ext4"
    assert mounts[1].health is None


def test_storage_collector_squashfs_rom_shape() -> None:
    """Real AC2350 shape: the read-only squashfs ``/rom`` firmware mount is
    reported at 100% alongside the writable overlay."""
    ctx = make_context(
        {
            "df -kPT": (
                "Filesystem     Type  1024-blocks    Used  Available Capacity Mounted on\n"
                "/dev/root      squashfs     5000    5000         0     100% /rom\n"
                "overlayfs:/overlay  overlay  30000  15000     15000      50% /overlay\n"
            ),
            "df -i": (
                "Filesystem      Inodes IUsed IFree IUse% Mounted on\n"
                "/dev/root         1024  1024     0   100% /rom\n"
                "overlayfs:/overlay 65536 3000 62536     5% /overlay\n"
            ),
        }
    )
    mounts = StorageCollector().collect(ctx)
    by_mount = {mount.mountpoint: mount for mount in mounts}
    rom = by_mount["/rom"]
    assert rom.filesystem == "squashfs"
    assert rom.use_percent == 100.0
    assert rom.health is None
    overlay = by_mount["/overlay"]
    assert overlay.filesystem == "overlay"
    assert overlay.use_percent == 50.0
    assert overlay.health == "ok"


def test_network_collector_from_ubus() -> None:
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                            "addresses": [
                                {"address": "192.168.1.1", "mask": 24, "proto": "static"}
                            ],
                        },
                        {
                            "interface": "wan",
                            "up": False,
                            "proto": "dhcp",
                            "device": "eth0",
                            "addresses": [],
                        },
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(
                {
                    "device": {
                        "br-lan": {
                            "up": True,
                            "link": True,
                            "speed": 1000,
                            "macaddress": "aa:bb:cc:dd:ee:ff",
                            "statistics": {"rx_bytes": 111, "tx_bytes": 222},
                        },
                        "eth0": {"up": False, "link": False, "speed": 0},
                    }
                }
            ),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    lan = interfaces[0]
    assert lan.addresses[0].address == "192.168.1.1"
    assert lan.addresses[0].prefix == 24
    assert lan.addresses[0].family == "ipv4"
    assert lan.link is True
    assert lan.speed_mbps == 1000
    assert lan.mac == "aa:bb:cc:dd:ee:ff"
    assert lan.rx_bytes == 111
    assert interfaces[1].up is False


def test_network_collector_fallback_to_ip() -> None:
    ctx = make_context(
        {
            "ip -o addr show": (
                "1: lo    inet 127.0.0.1/8 scope host lo\\       valid_lft forever\n"
                "2: br-lan    inet 192.168.1.1/24 brd 192.168.1.255 scope global br-lan\n"
            )
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    assert [i.name for i in interfaces] == ["lo", "br-lan"]
    assert interfaces[1].addresses[0].address == "192.168.1.1"


def test_firewall_collector() -> None:
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@defaults[0]=defaults\n"
                "firewall.@defaults[0].input='REJECT'\n"
                "firewall.@defaults[0].output='ACCEPT'\n"
                "firewall.@defaults[0].forward='REJECT'\n"
                "firewall.@defaults[0].masq='1'\n"
                "firewall.@defaults[0].synflood_protect='1'\n"
                "firewall.@zone[0]=zone\n"
                "firewall.@zone[0].name='lan'\n"
                "firewall.@zone[0].input='ACCEPT'\n"
                "firewall.@zone[0].output='ACCEPT'\n"
                "firewall.@zone[0].forward='ACCEPT'\n"
                "firewall.@zone[0].masq='1'\n"
                "firewall.@zone[0].mtu_fix='1'\n"
                "firewall.@zone[0].network='lan'\n"
                "firewall.@zone[1]=zone\n"
                "firewall.@zone[1].name='wan'\n"
                "firewall.@zone[1].network='wan'\n"
                "firewall.@zone[1].network='wan6'\n"
                "firewall.@rule[0]=rule\n"
                "firewall.@rule[0].name='Allow-DHCP-Renew'\n"
                "firewall.@rule[0].src='wan'\n"
                "firewall.@rule[0].dest='lan'\n"
                "firewall.@rule[0].proto='udp'\n"
                "firewall.@rule[0].dest_port='68'\n"
                "firewall.@rule[0].target='ACCEPT'\n"
                "firewall.@rule[1]=rule\n"
                "firewall.@rule[1].name='Drop-bad'\n"
                "firewall.@rule[1].enabled='0'\n"
                "firewall.@rule[1].target='DROP'\n"
                "firewall.@redirect[0]=redirect\n"
                "firewall.@redirect[0].name='Web'\n"
                "firewall.@redirect[0].src='wan'\n"
                "firewall.@redirect[0].src_dport='80'\n"
                "firewall.@redirect[0].dest='lan'\n"
                "firewall.@redirect[0].dest_ip='192.168.1.50'\n"
                "firewall.@redirect[0].dest_port='8080'\n"
                "firewall.@redirect[0].proto='tcp'\n"
                "firewall.@nat[0]=nat\n"
                "firewall.@nat[0].name='snat'\n"
                "firewall.@nat[0].target='SNAT'\n"
                "firewall.@nat[0].src='lan'\n"
                "firewall.@nat[0].dest_ip='10.0.0.2'\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "fw4 1.0.1\n",
            "cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null": "648\n",
            "cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null": "65536\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert info.defaults.input == "REJECT"
    assert info.defaults.forward == "REJECT"
    assert info.defaults.masquerade is True
    assert info.defaults.syn_flood is True
    assert info.zones[0].name == "lan"
    assert info.zones[0].input == "ACCEPT"
    assert info.zones[0].masquerade is True
    assert info.zones[0].mtu_fix is True
    assert info.zones[0].network == ["lan"]
    assert info.zones[1].network == ["wan", "wan6"]
    assert info.rules[0].name == "Allow-DHCP-Renew"
    assert info.rules[0].target == "ACCEPT"
    assert info.rules[0].dest_port == "68"
    assert info.rules[0].enabled is True
    assert info.rules[0].section == "@rule[0]"
    assert info.rules[1].enabled is False
    assert info.forwards[0].name == "Web"
    assert info.forwards[0].dest_ip == "192.168.1.50"
    assert info.forwards[0].src_dport == "80"
    assert info.nat[0].target == "SNAT"
    assert info.status.running is False
    assert info.status.version == "fw4 1.0.1"
    assert info.conntrack is not None
    assert info.conntrack.count == 648
    assert info.conntrack.max == 65536


def test_wifi_collector() -> None:
    ctx = make_context(
        {
            "ubus call wifi status": json.dumps(
                {
                    "radio0": {
                        "up": True,
                        "config": {
                            "hwmode": "11ax",
                            "channel": "6",
                            "txpower": "20",
                            "frequency": "2437",
                        },
                        "interfaces": [{"config": {"ssid": "HomeNet"}}],
                        "stations": {
                            "11:22:33:44:55:66": {
                                "signal": -50,
                                "txbytes": 100,
                                "rxbytes": 200,
                                "connected_time": 300,
                            }
                        },
                    }
                }
            )
        }
    )
    wifi = WifiCollector().collect(ctx)
    assert wifi.radios[0].ssid == "HomeNet"
    assert wifi.radios[0].channel == 6
    assert wifi.radios[0].band == "2.4GHz"
    assert wifi.radios[0].station_count == 1
    assert wifi.clients[0].mac == "11:22:33:44:55:66"
    assert wifi.clients[0].signal_dbm == -50
    assert wifi.clients[0].connected_minutes == 300


def test_wifi_collector_ssids_and_stations() -> None:
    ctx = make_context(
        {
            "ubus call wifi status": json.dumps(
                {
                    "radio0": {
                        "up": True,
                        "config": {
                            "hwmode": "11ax",
                            "channel": "36",
                            "txpower": "17",
                            "frequency": "5180",
                            "device": "radio0",
                        },
                        "interfaces": [
                            {"config": {"device": "radio0", "ssid": "Home", "ifname": "phy0-ap0"}}
                        ],
                        "stations": {
                            "11:22:33:44:55:66": {
                                "signal": -48,
                                "noise": -96,
                                "txbytes": 100,
                                "rxbytes": 200,
                                "tx_rate": 180000000,
                                "rx_rate": 390000000,
                                "connected_time": 300,
                            },
                            "aa:bb:cc:dd:ee:ff": {
                                "signal": -62,
                                "noise": -96,
                                "txbytes": 50,
                                "rxbytes": 90,
                                "connected_time": 120,
                            },
                        },
                    }
                }
            ),
            "uci show wireless": (
                "wireless=wireless\n"
                "wireless.radio0=wifi-device\n"
                "wireless.radio0.type='mac80211'\n"
                "wireless.radio0.path='1e140000.pcie'\n"
                "wireless.radio0.country='DE'\n"
                "wireless.radio0.htmode='VHT80'\n"
                "wireless.radio0.hwmode='11a'\n"
                "wireless.radio0.channel='36'\n"
                "wireless.radio0.txpower='17'\n"
                "wireless.home=wifi-iface\n"
                "wireless.home.device='radio0'\n"
                "wireless.home.network='lan'\n"
                "wireless.home.mode='ap'\n"
                "wireless.home.ssid='Home'\n"
                "wireless.home.encryption='psk2'\n"
                "wireless.guest=wifi-iface\n"
                "wireless.guest.device='radio0'\n"
                "wireless.guest.network='guest'\n"
                "wireless.guest.mode='ap'\n"
                "wireless.guest.ssid='Guest'\n"
                "wireless.guest.disabled='1'\n"
            ),
            "iw dev phy0-ap0 station dump 2>/dev/null": (
                "Station 11:22:33:44:55:66 (on phy0-ap0)\nStation aa:bb:cc:dd:ee:ff (on phy0-ap0)\n"
            ),
        }
    )
    wifi = WifiCollector().collect(ctx)
    assert wifi.radios[0].country == "DE"
    assert wifi.radios[0].hardware == "1e140000.pcie"
    assert wifi.radios[0].channel == 36
    assert wifi.radios[0].width_mhz == 80
    assert wifi.radios[0].band == "5GHz"

    by_ssid = {net.ssid: net for net in wifi.networks}
    assert set(by_ssid) == {"Home", "Guest"}
    assert by_ssid["Home"].interface == "phy0-ap0"
    assert by_ssid["Home"].enabled is True
    assert by_ssid["Home"].client_count == 2
    assert by_ssid["Home"].encryption == "psk2"
    assert by_ssid["Guest"].enabled is False
    assert by_ssid["Guest"].client_count == 0
    assert by_ssid["Guest"].section == "guest"

    assert len(wifi.clients) == 2
    client = next(c for c in wifi.clients if c.mac == "11:22:33:44:55:66")
    assert client.noise == -96
    assert client.rx_rate == 390000000
    assert client.tx_rate == 180000000
    assert client.connected_time == 300
    assert client.interface == "phy0-ap0"


def test_wifi_collector_falls_back_to_uci_and_live_interfaces() -> None:
    """Real AC2350 shape: ``ubus call wifi status`` is unavailable (exit 4), so
    radios must be discovered from the UCI ``wifi-device`` sections and the live
    kernel wireless interfaces (``phy0-ap0``/``phy1-ap0``)."""
    ctx = make_context(
        {
            # No "ubus call wifi status" entry -> the ubus call raises and the
            # collector falls back.
            "uci show wireless": (
                "wireless=wireless\n"
                "wireless.radio0=wifi-device\n"
                "wireless.radio0.name='phy0'\n"
                "wireless.radio0.type='mac80211'\n"
                "wireless.radio0.path='1e140000.pcie'\n"
                "wireless.radio0.htmode='VHT80'\n"
                "wireless.radio0.hwmode='11a'\n"
                "wireless.radio0.channel='36'\n"
                "wireless.radio0.ssid0=wifi-iface\n"
                "wireless.radio0.ssid0.device='radio0'\n"
                "wireless.radio0.ssid0.mode='ap'\n"
                "wireless.radio0.ssid0.ssid='Xiaomi_5G'\n"
                "wireless.radio0.ssid0.encryption='psk2'\n"
                "wireless.radio1=wifi-device\n"
                "wireless.radio1.name='phy1'\n"
                "wireless.radio1.type='mac80211'\n"
                "wireless.radio1.path='1e140000.pcie1'\n"
                "wireless.radio1.htmode='HT40'\n"
                "wireless.radio1.hwmode='11g'\n"
                "wireless.radio1.channel='6'\n"
                "wireless.radio1.ssid1=wifi-iface\n"
                "wireless.radio1.ssid1.device='radio1'\n"
                "wireless.radio1.ssid1.mode='ap'\n"
                "wireless.radio1.ssid1.ssid='Xiaomi_2G'\n"
                "wireless.radio1.ssid1.encryption='psk2'\n"
            ),
            "for i in /sys/class/net/*; do": (
                "phy0-ap0|phy0|1|0x1003|2|/sys/devices/1e140000.pcie\n"
                "phy1-ap0|phy1|1|0x1003|1|/sys/devices/1e140000.pcie1\n"
            ),
            "iw dev phy0-ap0 station dump 2>/dev/null": (
                "Station 11:22:33:44:55:66 (on phy0-ap0)\n"
                "Station aa:bb:cc:dd:ee:ff (on phy0-ap0)\n"
            ),
            "iw dev phy1-ap0 station dump 2>/dev/null": (
                "Station cc:dd:ee:ff:00:11 (on phy1-ap0)\n"
            ),
        }
    )
    wifi = WifiCollector().collect(ctx)

    assert len(wifi.radios) == 2
    by_name = {radio.name: radio for radio in wifi.radios}
    radio0 = by_name["radio0"]
    assert radio0.up is True
    assert radio0.band == "5GHz"
    assert radio0.channel == 36
    assert radio0.width_mhz == 80
    assert radio0.station_count == 2
    assert radio0.ssid == "Xiaomi_5G"
    assert radio0.hardware == "1e140000.pcie"
    radio1 = by_name["radio1"]
    assert radio1.up is True
    assert radio1.band == "2.4GHz"
    assert radio1.station_count == 1
    assert radio1.ssid == "Xiaomi_2G"

    by_ssid = {net.ssid: net for net in wifi.networks}
    assert set(by_ssid) == {"Xiaomi_5G", "Xiaomi_2G"}
    assert by_ssid["Xiaomi_5G"].interface == "phy0-ap0"
    assert by_ssid["Xiaomi_5G"].client_count == 2
    assert by_ssid["Xiaomi_5G"].encryption == "psk2"
    assert by_ssid["Xiaomi_2G"].interface == "phy1-ap0"
    assert by_ssid["Xiaomi_2G"].client_count == 1

    # Even without ubus, the fallback surfaces the associated stations so the
    # frontend can classify them as wireless clients.
    assert len(wifi.clients) == 3
    by_mac = {client.mac: client for client in wifi.clients}
    assert by_mac["11:22:33:44:55:66"].interface == "phy0-ap0"
    assert by_mac["11:22:33:44:55:66"].ssid == "Xiaomi_5G"
    assert by_mac["aa:bb:cc:dd:ee:ff"].interface == "phy0-ap0"
    assert by_mac["cc:dd:ee:ff:00:11"].interface == "phy1-ap0"
    assert by_mac["cc:dd:ee:ff:00:11"].ssid == "Xiaomi_2G"


def test_wifi_collector_live_radios_match_by_sysfs_path() -> None:
    """Real AC2350 UCI shape: ``wifi-device`` sections carry a ``path`` and
    ``band`` but no ``name``/``ifname``, and the live wireless interfaces expose
    a ``phy80211`` symlink (no ``wireless`` dir). Radios must still be matched
    to their live interfaces via the sysfs device path and reported as UP with
    station counts."""
    ctx = make_context(
        {
            # No "ubus call wifi status" entry -> fallback path.
            "uci show wireless": (
                "wireless=wireless\n"
                "wireless.radio0=wifi-device\n"
                "wireless.radio0.type='mac80211'\n"
                "wireless.radio0.path='pci0000:00/0000:00:00.0'\n"
                "wireless.radio0.band='5g'\n"
                "wireless.radio0.channel='36'\n"
                "wireless.radio0.htmode='VHT80'\n"
                "wireless.default_radio0=wifi-iface\n"
                "wireless.default_radio0.device='radio0'\n"
                "wireless.default_radio0.mode='ap'\n"
                "wireless.default_radio0.ssid='Nisa-Hira-1'\n"
                "wireless.default_radio0.encryption='psk2'\n"
                "wireless.radio1=wifi-device\n"
                "wireless.radio1.type='mac80211'\n"
                "wireless.radio1.path='platform/ahb/18100000.wmac'\n"
                "wireless.radio1.band='2g'\n"
                "wireless.radio1.channel='1'\n"
                "wireless.radio1.htmode='HT20'\n"
                "wireless.default_radio1=wifi-iface\n"
                "wireless.default_radio1.device='radio1'\n"
                "wireless.default_radio1.mode='ap'\n"
                "wireless.default_radio1.ssid='Nisa-Hira-1'\n"
                "wireless.default_radio1.encryption='psk2'\n"
            ),
            "for i in /sys/class/net/*; do": (
                "phy0-ap0|phy0|1|0x1303|1|/sys/devices/pci0000:00/0000:00:00.0\n"
                "phy1-ap0|phy1|1|0x1303|0|/sys/devices/platform/ahb/18100000.wmac\n"
            ),
            "iw dev phy0-ap0 station dump 2>/dev/null": (
                "Station 11:22:33:44:55:66 (on phy0-ap0)\n"
            ),
        }
    )
    wifi = WifiCollector().collect(ctx)

    by_name = {radio.name: radio for radio in wifi.radios}
    assert set(by_name) == {"radio0", "radio1"}
    radio0 = by_name["radio0"]
    assert radio0.up is True
    assert radio0.band == "5GHz"
    assert radio0.channel == 36
    assert radio0.station_count == 1
    assert radio0.ssid == "Nisa-Hira-1"
    assert radio0.hardware == "pci0000:00/0000:00:00.0"
    radio1 = by_name["radio1"]
    assert radio1.up is True
    assert radio1.band == "2.4GHz"
    assert radio1.channel == 1
    assert radio1.station_count == 0
    assert radio1.hardware == "platform/ahb/18100000.wmac"

    by_ssid = {net.ssid: net for net in wifi.networks}
    assert set(by_ssid) == {"Nisa-Hira-1"}
    nets = {net.radio: net for net in wifi.networks}
    assert nets["radio0"].interface == "phy0-ap0"
    assert nets["radio0"].client_count == 1
    # Zero-station radio1: no live station count, so no interface is attached.
    assert nets["radio1"].interface is None
    assert nets["radio1"].client_count == 0


def test_wifi_collector_surfaces_live_radios_without_uci_config() -> None:
    """Radios present in the kernel but absent from UCI (unmanaged hardware)
    are still reported so genuinely available radios are never missed."""
    ctx = make_context(
        {
            "uci show wireless": "wireless=wireless\n",
            "for i in /sys/class/net/*; do": (
                "phy0-ap0|phy0|1|0x1003|0\n"
                "wlan1|phy1|0|0x1000|0\n"
            ),
        }
    )
    wifi = WifiCollector().collect(ctx)
    by_name = {radio.name: radio for radio in wifi.radios}
    assert set(by_name) == {"phy0", "phy1"}
    assert by_name["phy0"].up is True
    assert by_name["phy1"].up is False


def test_wifi_collector_does_not_invent_radios() -> None:
    """No UCI devices and no live wireless interfaces -> no radios at all."""
    ctx = make_context({"uci show wireless": "wireless=wireless\n"})
    wifi = WifiCollector().collect(ctx)
    assert wifi.radios == []
    assert wifi.networks == []
    assert wifi.clients == []


def test_clients_collector() -> None:
    ctx = make_context(
        {
            "ubus call dhcp leases": json.dumps(
                {
                    "leases": [
                        {
                            "hostname": "laptop",
                            "ip": "192.168.1.50",
                            "mac": "aa:bb:cc:dd:ee:01",
                            "expires": 999,
                        }
                    ]
                }
            )
        }
    )
    clients = ClientsCollector().collect(ctx)
    assert clients[0].hostname == "laptop"
    assert clients[0].ip == "192.168.1.50"


def test_arp_collector() -> None:
    ctx = make_context(
        {
            "cat /proc/net/arp": (
                "IP address       HW type     Flags       HW address            Mask     Device\n"
                "192.168.1.50     0x1         0x2         aa:bb:cc:dd:ee:01     *        br-lan\n"
            )
        }
    )
    entries = ArpCollector().collect(ctx)
    assert entries[0].ip == "192.168.1.50"
    assert entries[0].mac == "aa:bb:cc:dd:ee:01"
    assert entries[0].interface == "br-lan"
    assert entries[0].state == "complete"


def test_neighbors_collector_parses_nd_cache() -> None:
    ctx = make_context(
        {
            "ip -6 neigh show": (
                "fe80::1 dev br-lan lladdr 88:22:11:aa:bb:cc router REACHABLE\n"
                "2001:db8:1::1234 dev br-lan lladdr 00:11:22:33:44:55 STALE\n"
                "fe80::2 dev br-lan FAILED\n"
            )
        }
    )
    entries = NeighborsCollector().collect(ctx)
    assert len(entries) == 3
    first = entries[0]
    assert first.ip == "fe80::1"
    assert first.mac == "88:22:11:aa:bb:cc"
    assert first.interface == "br-lan"
    assert first.state == "reachable"
    assert first.family == "ipv6"
    assert entries[1].state == "stale"
    assert entries[2].mac is None
    assert entries[2].state is None


def test_routing_collector() -> None:
    ctx = make_context(
        {
            "ip -o route show": "default via 192.168.1.1 dev eth0 proto static metric 100\n",
            "ip -o -6 route show": "2001:db8::/64 dev br-lan proto ra metric 1024\n",
        }
    )
    routes = RoutingCollector().collect(ctx)
    assert routes[0].destination == "default"
    assert routes[0].gateway == "192.168.1.1"
    assert routes[0].metric == 100
    assert routes[0].family == "ipv4"
    assert routes[1].family == "ipv6"


def test_vpn_collector_wireguard() -> None:
    ctx = make_context(
        {
            "wg show all interfaces": (
                "wg0:\tpublic-key: PUBKEY\n"
                "wg0:\tlisten-port: 51820\n"
                "wg0:\tpeer: PEERKEY\n"
                "wg0:\tendpoint: 203.0.113.1:51820\n"
                "wg0:\tallowed-ips: 10.0.0.0/24, 10.0.1.0/24\n"
            ),
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wg0",
                            "up": True,
                            "proto": "wireguard",
                            "addresses": [{"address": "10.0.0.2", "mask": 32}],
                        }
                    ]
                }
            ),
            "uci show openvpn": "",
        }
    )
    tunnels = VpnCollector().collect(ctx)
    assert len(tunnels) == 1
    wg = tunnels[0]
    assert wg.kind == "wireguard"
    assert wg.up is True
    assert wg.public_key == "PUBKEY"
    assert wg.listen_port == 51820
    assert wg.peer_count == 1
    assert wg.addresses == ["10.0.0.2"]
    assert wg.detail["peers"][0]["endpoint"] == "203.0.113.1:51820"


def test_vpn_collector_wireguard_runtime_enrichment() -> None:
    ctx = make_context(
        {
            "wg show all interfaces": (
                "wg0:\tpublic-key: PUBKEY\n"
                "wg0:\tlisten-port: 51820\n"
                "wg0:\tpeer: PEERKEY\n"
                "wg0:\tendpoint: 203.0.113.1:51820\n"
                "wg0:\tallowed-ips: 10.0.0.0/24, 10.0.1.0/24\n"
            ),
            "wg show all latest-handshakes 2>/dev/null": (
                "wg0\tPEERKEY\t1700000000\n"
            ),
            "wg show all transfer 2>/dev/null": "wg0\tPEERKEY\t1000\t2000\n",
            "wg show all persistent-keepalive 2>/dev/null": "wg0\tPEERKEY\t25\n",
            "ubus call network.interface dump": json.dumps({"interface": []}),
            "uci show openvpn": "",
        }
    )
    tunnels = VpnCollector().collect(ctx)
    peers = tunnels[0].detail["peers"]
    assert peers[0]["latest_handshake"] == 1700000000
    assert peers[0]["persistent_keepalive"] == 25
    assert peers[0]["rx_bytes"] == 1000
    assert peers[0]["tx_bytes"] == 2000
    assert tunnels[0].rx_bytes == 1000
    assert tunnels[0].tx_bytes == 2000
    assert tunnels[0].detail["latest_handshake"] == 1700000000


def test_vpn_collector_openvpn_config() -> None:
    ctx = make_context(
        {
            "wg show all interfaces": "",
            "ubus call network.interface dump": json.dumps({"interface": []}),
            "uci show openvpn": (
                "openvpn.myserver=openvpn\n"
                "openvpn.myserver.enabled='1'\n"
                "openvpn.myserver.remote='vpn.example.com'\n"
                "openvpn.myserver.port='1194'\n"
                "openvpn.myserver.mode='client'\n"
            ),
        }
    )
    tunnels = VpnCollector().collect(ctx)
    assert len(tunnels) == 1
    assert tunnels[0].kind == "openvpn"
    assert tunnels[0].endpoint == "vpn.example.com:1194"
    assert tunnels[0].up is True


def test_dhcp_collector() -> None:
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.@dnsmasq[0]=dnsmasq\n"
                "dhcp.@dnsmasq[0].enable_dnsmasq='1'\n"
                "dhcp.@dhcp[0]=dhcp\n"
                "dhcp.@dhcp[0].interface='lan'\n"
                "dhcp.@dhcp[0].start='100'\n"
                "dhcp.@dhcp[0].limit='150'\n"
                "dhcp.@dhcp[0].leasetime='12h'\n"
            ),
            "ubus call dhcp leases": json.dumps(
                {"leases": [{"hostname": "tv", "ip": "192.168.1.120", "mac": "aa:bb:cc:00:00:01"}]}
            ),
        }
    )
    info = DhcpCollector().collect(ctx)
    assert info.enabled is True
    assert info.pools[0].interface == "lan"
    assert info.pools[0].limit == 150
    assert info.leases[0].hostname == "tv"


def test_packages_collector() -> None:
    ctx = make_context(
        {
            "opkg list-installed": (
                "base-files - 258-r26317-80e097e2a7 - Base filesystem for OpenWrt\n"
                "luci - 1:25.0.0~20241114-1 - LuCI - OpenWrt Configuration Interface\n"
            )
        }
    )
    packages = PackagesCollector().collect(ctx)
    assert packages[0].name == "base-files"
    assert packages[0].version == "258-r26317-80e097e2a7"
    assert packages[1].name == "luci"


def test_kernel_collector() -> None:
    ctx = make_context(
        {
            "ubus call system board": json.dumps(
                {
                    "architecture": "x86_64",
                    "board_name": "x86/64",
                    "hostname": "OpenWrt",
                    "kernel": "6.6.80",
                    "model": "Generic x86/64",
                    "release": "SNAPSHOT",
                    "system": "Generic",
                    "version": "1.0",
                }
            )
        }
    )
    kernel = KernelCollector().collect(ctx)
    assert kernel.kernel == "6.6.80"
    assert kernel.model == "Generic x86/64"
    assert ctx.state["system.board"]["hostname"] == "OpenWrt"


def test_kernel_collector_parses_release_dict() -> None:
    """Modern OpenWrt ``ubus system board`` returns ``release`` as a dict; the
    collector must expose structured fields instead of a raw dict repr."""
    ctx = make_context(
        {
            "ubus call system board": json.dumps(
                {
                    "architecture": "MIPS 74Kc V5.4",
                    "board_name": "xiaomi,mi-router-ac2350",
                    "hostname": "OpenWrt",
                    "kernel": "5.15.160",
                    "model": "Xiaomi Mi Router AC2350",
                    "release": {
                        "distribution": "OpenWrt",
                        "version": "25.12.0",
                        "revision": "r32713-f919e7899d",
                        "target": "ath79/generic",
                        "description": "OpenWrt 25.12.0 r32713-f919e7899d",
                    },
                    "system": "Qualcomm Atheros QCA956X ver 1 rev 0",
                }
            )
        }
    )
    kernel = KernelCollector().collect(ctx)
    assert kernel.distribution == "OpenWrt"
    assert kernel.release_version == "25.12.0"
    assert kernel.revision == "r32713-f919e7899d"
    assert kernel.target == "ath79/generic"
    assert kernel.release_description == "OpenWrt 25.12.0 r32713-f919e7899d"
    assert kernel.release == "OpenWrt 25.12.0 r32713-f919e7899d"
    assert "{" not in kernel.release
    assert "distribution" not in kernel.release


def test_kernel_collector_tolerates_string_release() -> None:
    """Legacy firmware returns a plain string for ``release``."""
    ctx = make_context(
        {
            "ubus call system board": json.dumps(
                {
                    "kernel": "5.10.110",
                    "release": "SNAPSHOT",
                    "version": "1.0",
                }
            )
        }
    )
    kernel = KernelCollector().collect(ctx)
    assert kernel.release == "SNAPSHOT"
    assert kernel.release_version == "SNAPSHOT"
    assert kernel.distribution is None
    assert kernel.revision is None


def test_logs_collector_parses_syslog_lines() -> None:
    ctx = make_context(
        {
            "logread -l 200": (
                "Mon Aug  1 23:04:41 2026 daemon.info hostapd[1234]: wlan0: new STA\n"
                "Mon Aug  1 23:04:41 2026 kern.warn kernel: [12345.678] nf_conntrack: warning\n"
                "bare line without a timestamp\n"
            )
        }
    )
    info = LogsCollector().collect(ctx)
    assert len(info.entries) == 3
    first = info.entries[0]
    assert first.facility == "daemon"
    assert first.priority == "info"
    assert first.ident == "hostapd[1234]"
    assert first.message == "wlan0: new STA"
    assert first.timestamp == "Mon Aug  1 23:04:41 2026"
    assert info.entries[2].message == "bare line without a timestamp"


def test_cpu_collector_captures_model_arch_and_temperature() -> None:
    ctx = make_context(
        {
            "ubus call system info": json.dumps({"load_1": 0.4, "load_5": 0.3, "load_15": 0.2}),
            "cat /proc/cpuinfo": (
                "processor : 0\n"
                "model name : Intel(R) Celeron(R) N5105\n"
                "processor : 1\n"
                "model name : Intel(R) Celeron(R) N5105\n"
            ),
            "ls /sys/class/thermal/": "thermal_zone0\n",
            "cat /sys/class/thermal/thermal_zone0/temp": "52000",
        }
    )
    cpu = CpuCollector().collect(ctx)
    assert cpu.cores == 2
    assert cpu.model == "Intel(R) Celeron(R) N5105"
    assert cpu.temperature_c == 52.0


def test_cpu_collector_architecture_from_kernel_state() -> None:
    ctx = make_context({"cat /proc/loadavg": "0.1 0.1 0.1 1/1 1"})
    ctx.state["kernel"] = type("K", (), {"architecture": "aarch64"})()
    cpu = CpuCollector().collect(ctx)
    assert cpu.architecture == "aarch64"


def test_memory_collector_reports_swap() -> None:
    ctx = make_context(
        {
            "cat /proc/meminfo": (
                "MemTotal:       500000 kB\n"
                "MemFree:        100000 kB\n"
                "SwapTotal:      200000 kB\n"
                "SwapFree:       150000 kB\n"
            )
        }
    )
    memory = MemoryCollector().collect(ctx)
    assert memory.swap_total_kb == 200000
    assert memory.swap_free_kb == 150000
    assert memory.swap_used_kb == 50000


def test_memory_collector_no_swap() -> None:
    ctx = make_context(
        {
            "cat /proc/meminfo": (
                "MemTotal:       500000 kB\n"
                "MemFree:        100000 kB\n"
                "SwapTotal:      0 kB\n"
                "SwapFree:       0 kB\n"
            )
        }
    )
    memory = MemoryCollector().collect(ctx)
    assert memory.swap_total_kb is None
    assert memory.swap_used_kb is None


def test_network_collector_detects_bridge_vlan_mtu_and_gateway() -> None:
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                            "addresses": [{"address": "192.168.1.1", "mask": 24}],
                        },
                        {
                            "interface": "lan.20",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan.20",
                            "addresses": [{"address": "10.0.20.1", "mask": 24}],
                        },
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0",
                            "addresses": [{"address": "203.0.113.10", "mask": 24}],
                        },
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(
                {
                    "device": {
                        "br-lan": {"up": True, "link": True, "mtu": 1500},
                        "br-lan.20": {"up": True, "link": True, "mtu": 1500},
                        "eth0": {"up": True, "link": True, "mtu": 1500},
                    }
                }
            ),
            "ip -o route show default": (
                "default via 203.0.113.1 dev eth0 proto static metric 100\n"
            ),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 1.1.1.1\nnameserver 8.8.8.8\n"
            ),
        }
    )
    network = NetworkCollector().collect(ctx)
    lan = next(i for i in network if i.name == "lan")
    vlan = next(i for i in network if i.name == "lan.20")
    wan = next(i for i in network if i.name == "wan")
    assert lan.is_bridge is True
    assert lan.mtu == 1500
    assert vlan.vlan_id == 20
    assert lan.gateway is None
    assert wan.gateway == "203.0.113.1"
    assert ctx.state["network_status"]["gateway"] == "203.0.113.1"
    assert ctx.state["network_status"]["dns"] == ["1.1.1.1", "8.8.8.8"]
    assert ctx.state["network_status"]["wan_interface"] == "eth0"


def test_wifi_collector_reports_channel_width() -> None:
    ctx = make_context(
        {
            "ubus call wifi status": json.dumps(
                {
                    "radio0": {
                        "up": True,
                        "config": {
                            "hwmode": "11ax",
                            "htmode": "HE80",
                            "channel": "36",
                            "frequency": "5180",
                        },
                        "interfaces": [{"config": {"ssid": "Foo"}}],
                        "stations": {},
                    }
                }
            )
        }
    )
    wifi = WifiCollector().collect(ctx)
    assert wifi.radios[0].width_mhz == 80


def test_packages_collector_falls_back_to_opkg() -> None:
    ctx = make_context(
        {"opkg list-installed": "base-files - 258-r26317-80e097e2a7 - Base filesystem\n"}
    )
    packages = PackagesCollector().collect(ctx)
    assert packages[0].name == "base-files"
    assert packages[0].version == "258-r26317-80e097e2a7"


def test_packages_collector_uses_apk_when_present() -> None:
    ctx = make_context(
        {
            "command -v apk": "/usr/bin/apk\n",
            "apk list --installed": ("base-files-258-r0\nluci-1:25.0.0\nlibcurl-8.10.1-r0\n"),
        }
    )
    packages = PackagesCollector().collect(ctx)
    names = {p.name for p in packages}
    assert names == {"base-files", "luci", "libcurl"}
    assert next(p for p in packages if p.name == "libcurl").version == "8.10.1-r0"


def test_services_collector_detects_running_enabled_configured() -> None:
    ctx = make_context(
        {
            "nft list ruleset 2>/dev/null": "table inet fw4\n",
            "/etc/init.d/firewall enabled 2>/dev/null": "/etc/rc.d/S19firewall\n",
            "uci show firewall 2>/dev/null": "firewall.@defaults[0]=defaults\n",
            "pgrep -x dnsmasq 2>/dev/null": "1234\n",
            "/etc/init.d/dnsmasq enabled 2>/dev/null": "/etc/rc.d/S50dnsmasq\n",
            "uci show dhcp 2>/dev/null": "dhcp.dnsmasq=dnsmasq\n",
            "pgrep -x dropbear 2>/dev/null": "",
            "/etc/init.d/dropbear enabled 2>/dev/null": "/etc/rc.d/S45dropbear\n",
            "uci show dropbear 2>/dev/null": "dropbear.@dropbear[0]=dropbear\n",
        }
    )
    services = {s.name: s for s in ServicesCollector().collect(ctx)}
    assert services["firewall"].running is True
    assert services["firewall"].enabled is True
    assert services["firewall"].configured is True
    assert services["dnsmasq"].running is True
    assert services["dnsmasq"].configured is True
    assert services["dropbear"].running is False
    assert services["dropbear"].configured is True
    # Unconfigured service reports as not configured.
    assert services["tailscale"].configured is False


def test_network_collector_real_shape_dns_auto_file() -> None:
    """`resolv.conf.auto` is the real upstream DNS file on modern OpenWrt."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                        }
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(_real_device_status()),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 127.0.0.1\n"
                "# Interface wan\nnameserver 192.168.1.1\n"
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["dns"] == ["127.0.0.1", "192.168.1.1"]


def _real_device_status() -> dict:
    """The actual ``ubus call network.device status`` shape on OpenWrt 23+.

    Devices are returned as a flat object keyed by device name, with string
    speed values (``"1000F"``), ``carrier`` for link state, ``macaddr``, and
    bridge members under ``bridge-members``.
    """
    return {
        "br-lan": {
            "up": True,
            "carrier": True,
            "type": "bridge",
            "devtype": "bridge",
            "speed": "1000F",
            "mtu": 1500,
            "macaddr": "88:c3:97:85:bb:68",
            "bridge-members": ["eth0.1", "phy0-ap0", "phy1-ap0"],
            "bridge-attributes": {"stp": False, "forward_delay": 8},
        },
        "eth0": {},
        "eth0.1": {"up": True, "carrier": True, "devtype": "vlan", "speed": "1000"},
        "eth0.2": {
            "up": True,
            "carrier": True,
            "type": "Network device",
            "speed": "1000F",
        },
    }


def test_network_collector_real_device_shape_flat() -> None:
    """Modern OpenWrt returns device status as a flat name->info object."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                            "ipv4-address": [{"address": "192.168.100.1", "mask": 24}],
                            "ipv6-address": [],
                        },
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                            "ipv4-address": [{"address": "192.168.1.109", "mask": 24}],
                            "route": [
                                {"target": "0.0.0.0", "nexthop": "192.168.1.1", "mask": 0}
                            ],
                        },
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(_real_device_status()),
            "ip -o route show default": "default via 192.168.1.1 dev eth0.2\n",
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    by_name = {i.name: i for i in interfaces}
    assert "lan" in by_name
    assert "wan" in by_name
    lan = by_name["lan"]
    assert lan.addresses[0].address == "192.168.100.1"
    assert lan.addresses[0].prefix == 24
    assert lan.link is True
    assert lan.mac == "88:c3:97:85:bb:68"
    assert lan.speed_mbps == 1000
    assert lan.mtu == 1500
    assert lan.is_bridge is True
    assert lan.bridge_members == ["eth0.1", "phy0-ap0", "phy1-ap0"]
    assert lan.vlan_id is None
    wan = by_name["wan"]
    assert wan.speed_mbps == 1000
    assert wan.device == "eth0.2"


def test_network_collector_real_shape_list_of_devices() -> None:
    """Firmware where device status is list-shaped still merges cleanly."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                        }
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(_real_device_status()),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    wan = next(i for i in interfaces if i.name == "wan")
    assert wan.device == "eth0.2"
    assert wan.up is True


def test_network_collector_malformed_device_does_not_crash() -> None:
    """One malformed device entry is skipped; the rest of the section survives."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                            "ipv4-address": [{"address": "192.168.100.1", "mask": 24}],
                        }
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(
                {
                    "br-lan": {
                        "up": True,
                        "carrier": True,
                        "mtu": "not-an-int",
                        "speed": {"nested": True},
                        "statistics": {"rx_bytes": "not-a-number", "tx_bytes": None},
                    }
                }
            ),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    lan = next(i for i in interfaces if i.name == "lan")
    assert lan.link is True
    assert lan.rx_bytes is None
    assert lan.tx_bytes is None
    assert lan.speed_mbps is None
    assert lan.mtu is None


def test_network_collector_missing_ipv6_key() -> None:
    """Interfaces without a ``ipv6-address`` key still list their IPv4."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                            "ipv4-address": [{"address": "192.168.1.109", "mask": 24}],
                        }
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(_real_device_status()),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    wan = next(i for i in interfaces if i.name == "wan")
    assert wan.addresses[0].address == "192.168.1.109"
    assert wan.addresses[0].family == "ipv4"


def test_network_collector_surfaces_standalone_devices() -> None:
    """Kernel/physical devices no interface references are still surfaced."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                        },
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                        },
                    ]
                }
            ),
            "ubus call network.device status": json.dumps(
                {
                    "br-lan": {
                        "up": True,
                        "carrier": True,
                        "type": "bridge",
                        "devtype": "bridge",
                        "speed": "1000F",
                        "mtu": 1500,
                        "macaddr": "88:c3:97:85:bb:68",
                        "bridge-members": ["eth0.1", "phy0-ap0", "phy1-ap0"],
                        "bridge-attributes": {"stp": False, "forward_delay": 8},
                    },
                    "eth0.2": {"up": True, "carrier": True, "speed": "1000F"},
                    "eth0": {"up": True, "carrier": True, "speed": "1000F"},
                    "phy0-ap0": {"up": True, "carrier": True, "type": "Network device"},
                }
            ),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    by_name = {i.name: i for i in interfaces}
    # eth0 and phy0-ap0 are referenced by no logical interface, so they
    # surface as standalone device entries for the UI to render.
    assert "eth0" in by_name
    eth0 = by_name["eth0"]
    assert eth0.proto is None
    assert eth0.device == "eth0"
    assert eth0.link is True
    assert eth0.speed_mbps == 1000
    assert by_name["phy0-ap0"].up is True
    # Bridge member metadata still flows to the bridge entry itself.
    assert by_name["lan"].bridge_members == ["eth0.1", "phy0-ap0", "phy1-ap0"]


# --------------------------------------------------------------------------- #
# WAN/LAN harden: default-route parsing, WAN by proto, unknown-uplink honesty   #
# --------------------------------------------------------------------------- #


def test_network_collector_link_scope_default_route_has_no_gateway() -> None:
    """``default dev eth0 scope link`` carries no gateway; only the device is heard."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0",
                            "ipv4-address": [{"address": "203.0.113.10", "mask": 24}],
                        }
                    ]
                }
            ),
            "ip -o route show default": "default dev eth0 scope link\n",
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    wan = next(i for i in interfaces if i.name == "wan")
    assert wan.gateway is None
    assert ctx.state["network_status"]["gateway"] is None
    assert ctx.state["network_status"]["wan_interface"] == "eth0"


def test_network_collector_ipv6_default_route_detects_uplink() -> None:
    """An IPv6-only uplink still yields a wan_interface via the IPv6 default route."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan6",
                            "up": True,
                            "proto": "dhcpv6",
                            "device": "eth0",
                            "ipv4-address": [],
                            "ipv6-address": [{"address": "2001:db8::10", "mask": 64}],
                        }
                    ]
                }
            ),
            "ip -o -6 route show default": "default via fe80::1 dev eth0 metric 1024\n",
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["wan_interface"] == "eth0"


def test_network_collector_wan_detected_by_proto_without_wan_name() -> None:
    """A cellular/misc WAN (no ``wan`` in the name) is recognized by its proto."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wwan0",
                            "up": True,
                            "proto": "qmi",
                            "device": "wwan0",
                            "ipv4-address": [{"address": "10.0.0.2", "mask": 32}],
                        },
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                            "ipv4-address": [{"address": "192.168.1.1", "mask": 24}],
                        },
                    ]
                }
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["wan_interface"] == "wwan0"


def test_network_collector_no_wan_does_not_misreport_lan() -> None:
    """Without a default route or WAN proto, wan_interface is None, not lan."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "proto": "static",
                            "device": "br-lan",
                            "ipv4-address": [{"address": "192.168.1.1", "mask": 24}],
                        }
                    ]
                }
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["wan_interface"] is None


def test_network_collector_survives_missing_device_status() -> None:
    """When ``network.device status`` is unavailable, interfaces must still be
    surfaced (link/speed/mac unknown) instead of dropping the whole section."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0",
                            "ipv4-address": [{"address": "203.0.113.10", "mask": 24}],
                        }
                    ]
                }
            ),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    assert len(interfaces) == 1
    wan = interfaces[0]
    assert wan.name == "wan"
    assert wan.up is True
    assert wan.device == "eth0"
    assert wan.mac is None
    assert wan.link is None
    assert wan.addresses[0].address == "203.0.113.10"


def test_network_collector_dns_deduplicated() -> None:
    """Repeated resolv.conf nameservers collapse to a stable unique list."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps({"interface": []}),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 1.1.1.1\nnameserver 1.1.1.1\nnameserver 8.8.8.8\n"
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["dns"] == ["1.1.1.1", "8.8.8.8"]


# --------------------------------------------------------------------------- #
# VPN harden: inactive-but-configured WireGuard, modern netifd address keys     #
# --------------------------------------------------------------------------- #


def test_vpn_collector_wireguard_configured_but_inactive_is_surfaced() -> None:
    """A WireGuard interface in the netifd dump stays visible even when ``wg``
    reports nothing (tool missing or interface down): configured-but-inactive."""
    ctx = make_context(
        {
            "wg show all interfaces": "",
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wg0",
                            "up": False,
                            "proto": "wireguard",
                            "device": "wg0",
                            "ipv4-address": [{"address": "10.0.0.1", "mask": 32}],
                        }
                    ]
                }
            ),
            "uci show openvpn": "",
        }
    )
    tunnels = VpnCollector().collect(ctx)
    assert len(tunnels) == 1
    wg = tunnels[0]
    assert wg.kind == "wireguard"
    assert wg.up is False
    assert wg.addresses == ["10.0.0.1"]
    assert wg.detail["state"] == "configured-but-inactive"


def test_vpn_collector_wireguard_netifd_modern_address_keys() -> None:
    """Modern OpenWrt reports addresses under ipv4-address/ipv6-address, not the
    legacy ``addresses`` key; both shapes must surface for a live tunnel."""
    ctx = make_context(
        {
            "wg show all interfaces": (
                "wg0:\tpublic-key: PUBKEY\n"
                "wg0:\tlisten-port: 51820\n"
                "wg0:\tpeer: PEERKEY\n"
            ),
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wg0",
                            "up": True,
                            "proto": "wireguard",
                            "ipv4-address": [{"address": "10.0.0.2", "mask": 32}],
                            "ipv6-address": [{"address": "fd00::2", "mask": 128}],
                        }
                    ]
                }
            ),
            "uci show openvpn": "",
        }
    )
    tunnels = VpnCollector().collect(ctx)
    assert tunnels[0].addresses == ["10.0.0.2", "fd00::2"]


def test_vpn_collector_openvpn_netifd_modern_address_keys() -> None:
    ctx = make_context(
        {
            "wg show all interfaces": "",
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "vpn0",
                            "up": True,
                            "proto": "openvpn",
                            "ipv4-address": [{"address": "10.8.0.1", "mask": 24}],
                        }
                    ]
                }
            ),
            "uci show openvpn": "",
        }
    )
    tunnels = VpnCollector().collect(ctx)
    assert len(tunnels) == 1
    assert tunnels[0].kind == "openvpn"
    assert tunnels[0].addresses == ["10.8.0.1"]


# --------------------------------------------------------------------------- #
# DHCP harden: named UCI sections (the stock OpenWrt shape)                     #
# --------------------------------------------------------------------------- #


def test_dhcp_collector_named_sections() -> None:
    """Stock OpenWrt uses named sections (``config dhcp 'lan'``); the type line
    (``dhcp.lan=dhcp``) must let pools and static host leases parse, and an
    odhcpd section must never be mistaken for a pool."""
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.lan=dhcp\n"
                "dhcp.lan.interface='lan'\n"
                "dhcp.lan.start='100'\n"
                "dhcp.lan.limit='150'\n"
                "dhcp.lan.leasetime='12h'\n"
                "dhcp.odhcpd=odhcpd\n"
                "dhcp.odhcpd.maindhcp='0'\n"
                "dhcp.printer=host\n"
                "dhcp.printer.name='printer'\n"
                "dhcp.printer.ip='192.168.1.99'\n"
                "dhcp.printer.mac='aa:bb:cc:00:00:02'\n"
                "dhcp.dnsmasq=dnsmasq\n"
                "dhcp.dnsmasq.enable_dnsmasq='1'\n"
            ),
            "ubus call dhcp leases": json.dumps({"leases": []}),
        }
    )
    info = DhcpCollector().collect(ctx)
    assert info.enabled is True
    assert len(info.pools) == 1
    pool = info.pools[0]
    assert pool.name == "lan"
    assert pool.interface == "lan"
    assert pool.limit == 150
    assert pool.range_end is None  # UCI ``start`` is an offset, not a full IP
    assert len(info.static_leases) == 1
    lease = info.static_leases[0]
    assert lease.hostname == "printer"
    assert lease.ip == "192.168.1.99"


# --------------------------------------------------------------------------- #
# WAN IP vs Public IP semantics + netifd dns-server parsing                    #
# --------------------------------------------------------------------------- #


def test_network_address_private_wan_is_not_public() -> None:
    """The real AC2350 WAN (192.168.1.121) is a private/CGNAT address — never
    labelled "Public IP". ``is_public`` must be False for RFC1918 space."""
    from router_agent.collectors.network import _is_public

    assert _is_public("192.168.1.121") is False
    assert _is_public("192.168.1.1") is False
    assert _is_public("10.0.0.2") is False
    assert _is_public("100.64.0.1") is False  # CGNAT
    assert _is_public("fe80::2aa:bbff:fe01:2340") is False  # link-local


def test_network_address_genuinely_public_is_public() -> None:
    """A genuinely globally-routable address must be labelled public."""
    from router_agent.collectors.network import _is_public

    assert _is_public("8.8.8.8") is True
    assert _is_public("1.1.1.1") is True
    assert _is_public("2001:4860:4860::8888") is True


def test_network_address_unparseable_neither_public_nor_private() -> None:
    """An unparseable address must never be guessed "public" — ``None``."""
    from router_agent.collectors.network import _is_public

    assert _is_public("") is None
    assert _is_public("not-an-ip") is None
    assert _is_public("999.1.1.1") is None


def test_network_collector_marks_is_public_on_interfaces() -> None:
    """The collector annotates every address with its public/private status."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                            "ipv4-address": [{"address": "192.168.1.121", "mask": 24}],
                            "ipv6-address": [],
                            "dns-server": ["192.168.1.1"],
                        },
                        {
                            "interface": "wan2",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.3",
                            "ipv4-address": [{"address": "8.8.8.8", "mask": 24}],
                            "ipv6-address": [],
                        },
                    ]
                }
            ),
            "ubus call network.device status": json.dumps({"eth0.2": {}, "eth0.3": {}}),
        }
    )
    interfaces = NetworkCollector().collect(ctx)
    by_name = {i.name: i for i in interfaces}
    assert by_name["wan"].addresses[0].is_public is False
    assert by_name["wan2"].addresses[0].is_public is True


def test_network_collector_dns_from_netifd_dns_server() -> None:
    """Netifd's authoritative per-interface ``dns-server`` list is used for the
    snapshot DNS (IPv4 and IPv6 upstream resolvers), not resolv.conf."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                            "ipv4-address": [{"address": "192.168.1.121", "mask": 24}],
                            "ipv6-address": [],
                            "dns-server": [
                                "192.168.1.1",
                                "fe80::2aa:bbff:fe01:2340",
                            ],
                        }
                    ]
                }
            ),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 127.0.0.1\n"  # loopback dnsmasq stub
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["dns"] == [
        "192.168.1.1",
        "fe80::2aa:bbff:fe01:2340",
    ]


def test_network_collector_dns_fallback_to_resolv_conf() -> None:
    """When netifd exposes no ``dns-server``, resolv.conf (upstream .auto files)
    still yields the real DNS so the display never goes empty."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                        }
                    ]
                }
            ),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 127.0.0.1\n"
                "# Interface wan\nnameserver 192.168.1.1\n"
                "nameserver 1.1.1.1\n"
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["dns"] == ["127.0.0.1", "192.168.1.1", "1.1.1.1"]


def test_network_collector_dns_missing_glob_does_not_erase_dns() -> None:
    """A non-matching ``/tmp/resolv.conf.d/*.conf`` glob must not fail the fallback
    command (``|| true``) — otherwise a missing file would silently drop DNS."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps({"interface": []}),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 8.8.4.4\n"
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["dns"] == ["8.8.4.4"]


def test_network_collector_dns_prefers_netifd_over_resolv_conf() -> None:
    """netifd dns-server wins even when resolv.conf reports only the loopback
    dnsmasq stub (the real-life AC2350 shape)."""
    ctx = make_context(
        {
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "wan",
                            "up": True,
                            "proto": "dhcp",
                            "device": "eth0.2",
                            "dns-server": ["192.168.1.1"],
                        }
                    ]
                }
            ),
            "cat /etc/resolv.conf 2>/dev/null; cat /tmp/resolv.conf.d/*.auto "
            "/tmp/resolv.conf.d/*.conf 2>/dev/null": (
                "nameserver 127.0.0.1\n"
            ),
        }
    )
    NetworkCollector().collect(ctx)
    assert ctx.state["network_status"]["dns"] == ["192.168.1.1"]


# --------------------------------------------------------------------------- #
# DHCP lease-file fallback, deduplication and range/DNS parsing                #
# --------------------------------------------------------------------------- #


def test_dhcp_collector_leases_fallback_to_lease_file() -> None:
    """``ubus call dhcp leases`` is missing on some dnsmasq builds (the AC2350
    returns "Method not found"); the collector must fall back to the dnsmasq
    lease file so the DHCP page never shows a false empty lease list."""
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.@dnsmasq[0]=dnsmasq\n"
                "dhcp.@dnsmasq[0].enable_dnsmasq='1'\n"
                "dhcp.lan=dhcp\n"
                "dhcp.lan.interface='lan'\n"
                "dhcp.lan.start='100'\n"
                "dhcp.lan.limit='150'\n"
            ),
            "cat /tmp/dhcp.leases 2>/dev/null": (
                "1786600513 e2:04:61:0e:d7:82 192.168.100.102 Redmi-Note-14 01:e2:04:61:0e:d7:82\n"
                "1786592633 88:e9:fe:64:fc:5c 192.168.100.215 Talats-MBP 01:88:e9:fe:64:fc:5c\n"
            ),
        }
    )
    info = DhcpCollector().collect(ctx)
    assert len(info.leases) == 2
    first = info.leases[0]
    assert first.hostname == "Redmi-Note-14"
    assert first.mac == "e2:04:61:0e:d7:82"
    assert first.ip == "192.168.100.102"
    assert first.expires == "1786600513"  # epoch preserved, not reformatted


def test_dhcp_collector_lease_file_asterisk_hostname_and_expiry() -> None:
    """A ``*`` hostname (client sent no name) renders as empty, and a numeric
    expiry is kept so consumers can distinguish active vs stale leases."""
    ctx = make_context(
        {
            "uci show dhcp": "dhcp.@dnsmasq[0]=dnsmasq\n",
            "cat /tmp/dhcp.leases 2>/dev/null": (
                "1786600513 aa:bb:cc:11:22:33 192.168.100.50 * 01:aa:bb:cc:11:22:33\n"
            ),
        }
    )
    info = DhcpCollector().collect(ctx)
    lease = info.leases[0]
    assert lease.hostname == ""
    assert lease.expires == "1786600513"
    assert lease.ip == "192.168.100.50"


def test_dhcp_collector_lease_deduplication() -> None:
    """A device appearing twice (e.g. stale entry after an IP change) collapses
    to a single lease; the newest (largest expiry) wins."""
    ctx = make_context(
        {
            "uci show dhcp": "dhcp.@dnsmasq[0]=dnsmasq\n",
            "cat /tmp/dhcp.leases 2>/dev/null": (
                "1786590000 88:e9:fe:64:fc:5c 192.168.100.215 old-ip 01:88:e9:fe:64:fc:5c\n"
                "1786600000 88:e9:fe:64:fc:5c 192.168.100.58 new-ip 01:88:e9:fe:64:fc:5c\n"
            ),
        }
    )
    info = DhcpCollector().collect(ctx)
    assert len(info.leases) == 1
    assert info.leases[0].ip == "192.168.100.58"
    assert info.leases[0].expires == "1786600000"


def test_dhcp_collector_lease_dedup_keeps_ubus_when_available() -> None:
    """ubus leases are preferred and deduplicated the same way."""
    ctx = make_context(
        {
            "uci show dhcp": "dhcp.@dnsmasq[0]=dnsmasq\n",
            "ubus call dhcp leases": json.dumps(
                {
                    "leases": [
                        {
                            "hostname": "tv",
                            "ip": "192.168.1.120",
                            "mac": "aa:bb:cc:00:00:01",
                            "expires": 100,
                        },
                        {
                            "hostname": "tv",
                            "ip": "192.168.1.121",
                            "mac": "aa:bb:cc:00:00:01",
                            "expires": 200,
                        },
                    ]
                }
            ),
        }
    )
    info = DhcpCollector().collect(ctx)
    assert len(info.leases) == 1
    assert info.leases[0].ip == "192.168.1.121"
    assert info.leases[0].expires == "200"


def test_clients_collector_falls_back_to_lease_file() -> None:
    """The clients collector shares the same fallback, so ``snapshot.clients``
    stays populated on firmware without the dhcp ubus leases method."""
    ctx = make_context(
        {
            "cat /tmp/dhcp.leases 2>/dev/null": (
                "1786600513 aa:bb:cc:11:22:33 192.168.100.50 laptop 01:aa:bb:cc:11:22:33\n"
            )
        }
    )
    clients = ClientsCollector().collect(ctx)
    assert clients[0].hostname == "laptop"
    assert clients[0].mac == "aa:bb:cc:11:22:33"


def test_dhcp_collector_pool_offset_range_resolution() -> None:
    """UCI ``start`` may be an offset (``100``); with the interface subnet from
    the live network dump the pool range resolves to real addresses."""
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.@dnsmasq[0]=dnsmasq\n"
                "dhcp.lan=dhcp\n"
                "dhcp.lan.interface='lan'\n"
                "dhcp.lan.start='100'\n"
                "dhcp.lan.limit='150'\n"
            ),
            "ubus call network.interface dump": json.dumps(
                {
                    "interface": [
                        {
                            "interface": "lan",
                            "up": True,
                            "device": "br-lan",
                            "ipv4-address": [{"address": "192.168.100.1", "mask": 24}],
                        }
                    ]
                }
            ),
            "cat /tmp/dhcp.leases 2>/dev/null": "",
        }
    )
    info = DhcpCollector().collect(ctx)
    pool = info.pools[0]
    assert pool.start == "192.168.100.100"
    assert pool.range_end == "192.168.100.249"


def test_dhcp_collector_pool_full_ip_range_when_start_is_absolute() -> None:
    """A full IPv4 ``start`` still resolves without needing the subnet."""
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.@dnsmasq[0]=dnsmasq\n"
                "dhcp.lan=dhcp\n"
                "dhcp.lan.interface='lan'\n"
                "dhcp.lan.start='192.168.50.10'\n"
                "dhcp.lan.limit='20'\n"
            ),
            "cat /tmp/dhcp.leases 2>/dev/null": "",
        }
    )
    info = DhcpCollector().collect(ctx)
    pool = info.pools[0]
    assert pool.start == "192.168.50.10"
    assert pool.range_end == "192.168.50.29"


def test_dhcp_collector_pool_level_dhcp_option() -> None:
    """``dhcp_option`` (gateway=3 / DNS=6) may live on the dhcp pool section
    (LuCI stores it there); both dnsmasq- and pool-level options must parse."""
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.@dnsmasq[0]=dnsmasq\n"
                "dhcp.@dnsmasq[0].domain='lan'\n"
                "dhcp.lan=dhcp\n"
                "dhcp.lan.interface='lan'\n"
                "dhcp.lan.dhcp_option='3,192.168.100.1'\n"
                "dhcp.lan.dhcp_option='6,192.168.100.1,1.1.1.1'\n"
            ),
            "cat /tmp/dhcp.leases 2>/dev/null": "",
        }
    )
    info = DhcpCollector().collect(ctx)
    assert info.gateway == "192.168.100.1"
    assert info.dns == ["192.168.100.1", "1.1.1.1"]
    assert info.domain == "lan"


def test_dhcp_collector_dnsmasq_level_dhcp_option_still_parses() -> None:
    """Global dnsmasq-level dhcp_option continues to work (legacy shape)."""
    ctx = make_context(
        {
            "uci show dhcp": (
                "dhcp.@dnsmasq[0]=dnsmasq\n"
                "dhcp.@dnsmasq[0].dhcp_option='3,192.168.1.1'\n"
                "dhcp.@dnsmasq[0].dhcp_option='6,8.8.8.8,8.8.4.4'\n"
            ),
            "cat /tmp/dhcp.leases 2>/dev/null": "",
        }
    )
    info = DhcpCollector().collect(ctx)
    assert info.gateway == "192.168.1.1"
    assert info.dns == ["8.8.8.8", "8.8.4.4"]


def test_dhcp_collector_no_leases_no_network_no_error() -> None:
    """No lease source and no network dump must produce empty results, not an
    exception or fabricated data."""
    ctx = make_context({"uci show dhcp": "dhcp.@dnsmasq[0]=dnsmasq\n"})
    info = DhcpCollector().collect(ctx)
    assert info.leases == []
    assert info.pools == []


# --------------------------------------------------------------------------- #
# Firewall hardening: single-line UCI lists, fw4 version, partial sections     #
# --------------------------------------------------------------------------- #


def test_firewall_collector_single_line_multi_value_lists() -> None:
    """``uci show firewall`` on OpenWrt 25.12 emits list options inside ONE
    quote pair (``network='wan' 'wan6'``). The collector must split those into
    a list instead of dropping the line entirely."""
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@zone[0]=zone\n"
                "firewall.@zone[0].name='lan'\n"
                "firewall.@zone[0].network='lan'\n"
                "firewall.@zone[1]=zone\n"
                "firewall.@zone[1].name='wan'\n"
                "firewall.@zone[1].network='wan' 'wan6'\n"
                "firewall.@zone[1].input='REJECT'\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "Usage:\n\n  /sbin/fw4 start|stop|reload\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    by_name = {zone.name: zone for zone in info.zones}
    assert by_name["lan"].network == ["lan"]
    assert by_name["wan"].network == ["wan", "wan6"]


def test_firewall_collector_accumulates_repeated_list_lines() -> None:
    """Legacy multi-line list form (``option='a'`` / ``option='b'``) still
    accumulates, so both output shapes are supported."""
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@zone[0]=zone\n"
                "firewall.@zone[0].name='wan'\n"
                "firewall.@zone[0].network='wan'\n"
                "firewall.@zone[0].network='wan6'\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert info.zones[0].network == ["wan", "wan6"]


def test_firewall_collector_fw4_usage_not_reported_as_version() -> None:
    """fw4's ``-v`` is a verbose flag: on the AC2350 it prints its usage text
    with exit 0. The version must be reported as unavailable, never ``Usage:``."""
    ctx = make_context(
        {
            "uci show firewall": "firewall.@zone[0]=zone\nfirewall.@zone[0].name='lan'\n",
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": (
                "Usage:\n\n  /sbin/fw4 [-v] [-q] start|stop|flush|restart|reload\n"
            ),
            "cat /proc/sys/net/netfilter/nf_conntrack_count 2>/dev/null": "569\n",
            "cat /proc/sys/net/netfilter/nf_conntrack_max 2>/dev/null": "15360\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert info.status.version is None
    assert info.conntrack is not None
    assert info.conntrack.count == 569
    assert info.conntrack.max == 15360


def test_firewall_collector_fw3_version_kept() -> None:
    """A genuine fw3 version string is preserved (the fw3 backend still uses
    ``-v`` to print its version)."""
    ctx = make_context(
        {
            "uci show firewall": "firewall.@zone[0]=zone\n",
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "fw3 - v3.6.2\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert info.status.version == "fw3 - v3.6.2"


def test_firewall_collector_rules_keep_ipv6_family() -> None:
    """IPv6 traffic rules are parsed and retain their ``family``."""
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@rule[0]=rule\n"
                "firewall.@rule[0].name='Allow-DHCPv6'\n"
                "firewall.@rule[0].src='wan'\n"
                "firewall.@rule[0].proto='udp'\n"
                "firewall.@rule[0].dest_port='546'\n"
                "firewall.@rule[0].family='ipv6'\n"
                "firewall.@rule[0].target='ACCEPT'\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "Usage:\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert info.rules[0].family == "ipv6"
    assert info.rules[0].dest_port == "546"
    assert info.rules[0].enabled is True


def test_firewall_collector_disabled_redirect_and_zone() -> None:
    """Disabled sections (redirect + zone) are reported as disabled, not dropped
    or falsely shown as active."""
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@zone[0]=zone\n"
                "firewall.@zone[0].name='guest'\n"
                "firewall.@zone[0].disabled='1'\n"
                "firewall.@redirect[0]=redirect\n"
                "firewall.@redirect[0].name='Web'\n"
                "firewall.@redirect[0].src='wan'\n"
                "firewall.@redirect[0].dest_ip='192.168.1.50'\n"
                "firewall.@redirect[0].dest_port='8080'\n"
                "firewall.@redirect[0].enabled='0'\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "Usage:\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert info.zones[0].enabled is False
    assert info.forwards[0].name == "Web"
    assert info.forwards[0].enabled is False
    assert info.forwards[0].dest_ip == "192.168.1.50"


def test_firewall_collector_zone_policies_and_masquerade() -> None:
    """Zone input/output/forward policies and per-zone masquerade are parsed
    (the AC2350 wan zone: input REJECT, output ACCEPT, forward DROP, masq)."""
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@zone[0]=zone\n"
                "firewall.@zone[0].name='wan'\n"
                "firewall.@zone[0].network='wan' 'wan6'\n"
                "firewall.@zone[0].input='REJECT'\n"
                "firewall.@zone[0].output='ACCEPT'\n"
                "firewall.@zone[0].forward='DROP'\n"
                "firewall.@zone[0].masq='1'\n"
                "firewall.@zone[0].mtu_fix='1'\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "Usage:\n",
        }
    )
    info = FirewallCollector().collect(ctx)
    zone = info.zones[0]
    assert zone.input == "REJECT"
    assert zone.output == "ACCEPT"
    assert zone.forward == "DROP"
    assert zone.masquerade is True
    assert zone.mtu_fix is True
    assert zone.network == ["wan", "wan6"]


def test_firewall_collector_malformed_partial_sections() -> None:
    """A bare section header with no options (or junk lines) is tolerated and
    yields a defaulted zone; unknown section types are ignored safely."""
    ctx = make_context(
        {
            "uci show firewall": (
                "firewall.@zone[0]=zone\n"
                "firewall.@zone[1]=zone\n"
                "firewall.@zone[1].name='lan'\n"
                "firewall.@custom=something\n"
                "garbage line that is not UCI\n"
            ),
            "fw4 -v 2>/dev/null || fw3 -v 2>/dev/null": "",
        }
    )
    info = FirewallCollector().collect(ctx)
    assert len(info.zones) == 2
    assert info.zones[0].name == ""  # bare section defaults to empty name
    assert info.zones[1].name == "lan"
    assert info.rules == []
    assert info.nat == []
