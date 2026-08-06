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
            "cat /etc/resolv.conf /tmp/resolv.conf.d/*.conf": (
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
