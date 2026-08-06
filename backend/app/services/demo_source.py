"""Simulated snapshot source for the live dashboard.

Produces a plausible, continuously-varying :class:`DeviceSnapshot` so the
dashboard renders meaningful live widgets without a physical router. Values
drift smoothly over wall-clock time (load, CPU, temperature, traffic, device
count), so bandwidth and gauges animate on every poll. Never touches the
network — used by default and in tests.
"""

from __future__ import annotations

import math
import time
from datetime import UTC, datetime

from router_agent.collectors import COLLECTOR_NAMES
from router_agent.model import (
    ArpEntry,
    CpuInfo,
    DeviceSnapshot,
    DhcpInfo,
    DhcpLease,
    DhcpPool,
    FirewallConntrack,
    FirewallDefaults,
    FirewallForward,
    FirewallInfo,
    FirewallNat,
    FirewallRule,
    FirewallStatus,
    FirewallZone,
    KernelInfo,
    LogEntry,
    LogInfo,
    MemoryInfo,
    NeighborEntry,
    NetworkAddress,
    NetworkInterface,
    NetworkStatus,
    Package,
    RouteEntry,
    ServiceInfo,
    SnapshotMeta,
    StorageMount,
    TemperatureReading,
    VpnTunnel,
    WifiClient,
    WifiInfo,
    WifiNetwork,
    WifiRadio,
)

_UPTIME_START = time.time()


def _wave(now: float, base: float, amp: float, period: float) -> float:
    return base + amp * math.sin(2 * math.pi * now / period)


def build_simulated_snapshot() -> DeviceSnapshot:
    """Return one deterministic-but-drifting snapshot of a fictional router."""
    now = time.time()
    t = now % 3600  # cycle over the last hour
    uptime = int(now - _UPTIME_START)

    cpu_usage = max(4.0, min(92.0, _wave(t, 34.0, 22.0, 60.0)))
    load_base = cpu_usage / 100.0 * 4.0
    load_1 = max(0.05, load_base + _wave(t, 0.1, 0.2, 17.0))

    total_kb = 8_192 * 1024
    used_kb = int(total_kb * cpu_usage / 100.0)
    available_kb = total_kb - used_kb

    rx_total = int(_wave(t, 1.2e9, 0.3e9, 90.0) + 40_000_000 * (now / 60.0))
    tx_total = int(_wave(t, 0.6e9, 0.2e9, 120.0) + 22_000_000 * (now / 60.0))
    lan_rx = rx_total - int(0.15e9)
    lan_tx = tx_total - int(0.05e9)

    wan_ip = f"203.0.113.{20 + int(t / 60) % 200}"
    gateway = "203.0.113.1"
    station_count = 3 + int(t / 45) % 3

    devices = [
        ("phone", "192.168.1.50", "aa:bb:cc:00:00:01"),
        ("laptop", "192.168.1.51", "aa:bb:cc:00:00:02"),
        ("tv", "192.168.1.52", "aa:bb:cc:00:00:03"),
        ("thermostat", "192.168.1.53", "aa:bb:cc:00:00:04"),
        ("desktop", "192.168.1.54", "aa:bb:cc:00:00:05"),
    ]
    active = devices[:station_count]

    snapshot = DeviceSnapshot(
        meta=SnapshotMeta(
            collected_at=datetime.now(UTC),
            device_id="demo-router",
            transport="simulated",
            host="",
            board="x86/64",
            model="Demo OpenWrt x86/64",
            firmware="SNAPSHOT",
            collectors_run=list(COLLECTOR_NAMES),
        ),
        cpu=CpuInfo(
            load_1=load_1,
            load_5=max(0.05, load_1 * 0.8),
            load_15=max(0.05, load_1 * 0.6),
            cores=4,
            uptime_seconds=float(uptime),
            usage_percent=cpu_usage,
            frequency_mhz=int(_wave(t, 2200.0, 400.0, 45.0)),
            model="Demo Intel Celeron N5105",
            architecture="x86_64",
            temperature_c=max(40.0, min(82.0, _wave(t, 56.0, 8.0, 80.0))),
        ),
        memory=MemoryInfo(
            total_kb=total_kb,
            free_kb=int(available_kb * 0.55),
            used_kb=used_kb,
            buffered_kb=int(total_kb * 0.04),
            cached_kb=int(total_kb * 0.18),
            available_kb=available_kb,
            swap_total_kb=2_097_152,
            swap_free_kb=2_097_152 - int(_wave(t, 40_000.0, 30_000.0, 240.0)),
            swap_used_kb=int(_wave(t, 40_000.0, 30_000.0, 240.0)),
        ),
        temperature=[
            TemperatureReading(
                zone="cpu-thermal",
                temperature_c=max(40.0, min(78.0, _wave(t, 54.0, 9.0, 75.0))),
            ),
            TemperatureReading(
                zone="wifi-radio0",
                temperature_c=max(38.0, min(70.0, _wave(t, 46.0, 6.0, 130.0))),
            ),
        ],
        storage=[
            StorageMount(
                device="ubi0:rootfs",
                mountpoint="/",
                filesystem="ubifs",
                total_bytes=128 * 1024**2,
                used_bytes=int(64 * 1024**2 + _wave(t, 8e6, 2e6, 300.0)),
                available_bytes=48 * 1024**2,
                use_percent=62.5,
                inodes_total=65536,
                inodes_used=30000,
                inodes_available=35536,
                inode_use_percent=46.0,
                wear=2048,
                health="ok",
            ),
            StorageMount(
                device="/dev/sda1",
                mountpoint="/mnt/usb",
                filesystem="ext4",
                total_bytes=64 * 1024**3,
                used_bytes=int(28 * 1024**3 + _wave(t, 3e9, 1e9, 600.0)),
                available_bytes=36 * 1024**3,
                use_percent=43.75,
                inodes_total=262144,
                inodes_used=20000,
                inodes_available=242144,
                inode_use_percent=8.0,
            ),
        ],
        network=[
            NetworkInterface(
                name="lan",
                up=True,
                proto="static",
                device="br-lan",
                mac="aa:bb:cc:dd:ee:01",
                link=True,
                speed_mbps=1000,
                mtu=1500,
                rx_bytes=lan_rx,
                tx_bytes=lan_tx,
                is_bridge=True,
                addresses=[NetworkAddress(address="192.168.1.1", prefix=24, family="ipv4")],
            ),
            NetworkInterface(
                name="wan",
                up=True,
                proto="dhcp",
                device="eth0",
                mac="aa:bb:cc:dd:ee:02",
                link=True,
                speed_mbps=1000,
                mtu=1500,
                rx_bytes=rx_total,
                tx_bytes=tx_total,
                gateway=gateway,
                addresses=[
                    NetworkAddress(address=wan_ip, prefix=24, family="ipv4"),
                    NetworkAddress(address="2001:db8:1::1", prefix=64, family="ipv6"),
                ],
            ),
        ],
        network_status=NetworkStatus(
            gateway=gateway,
            dns=["1.1.1.1", "8.8.8.8"],
            wan_interface="eth0",
        ),
        firewall=FirewallInfo(
            defaults=FirewallDefaults(
                input="REJECT",
                output="ACCEPT",
                forward="REJECT",
                masquerade=True,
                syn_flood=True,
                osf=True,
                mtu=1452,
            ),
            zones=[
                FirewallZone(
                    name="lan",
                    input="ACCEPT",
                    output="ACCEPT",
                    forward="ACCEPT",
                    network=["lan"],
                    mtu_fix=True,
                ),
                FirewallZone(
                    name="wan",
                    input="REJECT",
                    output="ACCEPT",
                    forward="REJECT",
                    masquerade=True,
                    network=["wan"],
                    mtu_fix=False,
                ),
            ],
            rules=[
                FirewallRule(
                    name="allow-dns",
                    src="lan",
                    dest="wan",
                    proto="tcp",
                    dest_port="53",
                    target="ACCEPT",
                    family="ipv4",
                    enabled=True,
                    section="@rule[0]",
                ),
                FirewallRule(
                    name="drop-invalid",
                    src="wan",
                    proto="tcp",
                    target="REJECT",
                    family="ipv4",
                    enabled=False,
                    section="@rule[1]",
                ),
            ],
            forwards=[
                FirewallForward(
                    name="web-vpn",
                    proto="tcp",
                    src="wan",
                    src_dport="8443",
                    dest="lan",
                    dest_ip="192.168.1.50",
                    dest_port="443",
                    target="DNAT",
                    enabled=True,
                    section="@redirect[0]",
                )
            ],
            nat=[
                FirewallNat(
                    name="wan-snat",
                    target="SNAT",
                    src="lan",
                    dest_ip="10.0.0.2",
                    enabled=True,
                    section="@nat[0]",
                )
            ],
            status=FirewallStatus(running=True, enabled=True, version="fw4 1"),
            conntrack=FirewallConntrack(count=648, max=65536),
        ),
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
                    ssid="Home",
                    hwmode="11g",
                    width_mhz=20,
                    station_count=station_count,
                    country="US",
                    hardware="1e140000.pcie",
                ),
                WifiRadio(
                    name="radio1",
                    up=True,
                    mode="ap",
                    band="5GHz",
                    channel=36,
                    frequency_mhz=5180,
                    tx_power=17,
                    ssid="Home-5G",
                    hwmode="11a",
                    width_mhz=80,
                    station_count=max(0, station_count - 2),
                    country="US",
                    hardware="1e140000.pcie",
                ),
            ],
            networks=[
                WifiNetwork(
                    ssid="Home",
                    radio="radio0",
                    interface="phy0-ap0",
                    mode="ap",
                    encryption="psk2",
                    enabled=True,
                    network="lan",
                    client_count=station_count,
                    section="@wifi-iface[0]",
                ),
                WifiNetwork(
                    ssid="Home-5G",
                    radio="radio1",
                    interface="phy1-ap0",
                    mode="ap",
                    encryption="psk2",
                    enabled=True,
                    network="lan",
                    client_count=max(0, station_count - 2),
                    section="@wifi-iface[1]",
                ),
                WifiNetwork(
                    ssid="Guest",
                    radio="radio0",
                    mode="ap",
                    encryption="none",
                    hidden=True,
                    enabled=False,
                    network="guest",
                    client_count=0,
                    section="@wifi-iface[2]",
                ),
            ],
            clients=[
                WifiClient(
                    mac=mac,
                    ssid="Home" if idx < 3 else "Home-5G",
                    signal_dbm=-38 - idx * 6,
                    noise=-95 - idx,
                    tx_rate=180000000 - idx * 10000000,
                    rx_rate=390000000 + idx * 20000000,
                    tx_bytes=int(1e8 / (idx + 1)),
                    rx_bytes=int(3e8 / (idx + 1)),
                    connected_minutes=40 + idx * 15,
                    connected_time=(40 + idx * 15) * 60,
                )
                for idx, (_, ip, mac) in enumerate(active)
            ],
        ),
        clients=[
            DhcpLease(hostname=name, ip=ip, mac=mac, expires="23:59:59", interface="lan")
            for name, ip, mac in active
        ],
        arp=[
            ArpEntry(ip=ip, mac=mac, interface="br-lan", state="REACHABLE") for _, ip, mac in active
        ],
        neighbors=[
            NeighborEntry(
                ip=f"2001:db8:1::{20 + idx}",
                mac=mac,
                interface="br-lan",
                state="reachable",
            )
            for idx, (_, _, mac) in enumerate(active)
        ],
        routing=[
            RouteEntry(
                destination="0.0.0.0/0",
                gateway=gateway,
                interface="wan",
                metric=100,
                family="ipv4",
                flags="UG",
            ),
            RouteEntry(
                destination="192.168.1.0/24", interface="lan", metric=0, family="ipv4", flags="U"
            ),
            RouteEntry(
                destination="2001:db8::/64", interface="lan", metric=0, family="ipv6", flags="U"
            ),
        ],
        vpn=[
            VpnTunnel(
                name="wg0",
                kind="wireguard",
                up=True,
                public_key="8oJ8...C9w=",
                listen_port=51820,
                peer_count=2,
                addresses=["10.7.0.1/24"],
                detail={
                    "peers": [
                        {
                            "public_key": "AAA",
                            "endpoint": "198.51.100.7:51820",
                            "allowed_ips": ["10.7.0.2/32"],
                        },
                        {
                            "public_key": "BBB",
                            "endpoint": "198.51.100.9:51820",
                            "allowed_ips": ["10.7.0.3/32"],
                        },
                    ]
                },
            ),
            VpnTunnel(name="office", kind="openvpn", up=False),
        ],
        dhcp=DhcpInfo(
            pools=[
                DhcpPool(
                    name="lan",
                    interface="br-lan",
                    start="192.168.1.100",
                    limit=150,
                    leasetime="12h",
                )
            ],
            leases=[
                DhcpLease(hostname=name, ip=ip, mac=mac, expires="23:59:59", interface="br-lan")
                for name, ip, mac in active
            ],
            enabled=True,
        ),
        packages=[
            Package(name="luci", version="23.05.5", description="OpenWrt UI"),
            Package(name="wireguard-tools", version="1.0.20210914-1"),
            Package(name="openssl-util", version="3.0.14-1"),
        ],
        services=[
            ServiceInfo(name="firewall", running=True, enabled=True, configured=True),
            ServiceInfo(name="dnsmasq", running=True, enabled=True, configured=True),
            ServiceInfo(name="odhcpd", running=True, enabled=True, configured=True),
            ServiceInfo(name="hostapd", running=True, enabled=True, configured=True),
            ServiceInfo(name="dropbear", running=True, enabled=True, configured=True),
            ServiceInfo(name="wireguard", running=True, enabled=False, configured=True),
            ServiceInfo(name="tailscale", running=False, enabled=False, configured=False),
            ServiceInfo(name="mwan3", running=False, enabled=False, configured=True),
            ServiceInfo(name="sqm", running=True, enabled=True, configured=True),
        ],
        kernel=KernelInfo(
            kernel="6.6.80",
            release="SNAPSHOT",
            hostname="demo-router",
            model="Demo OpenWrt x86/64",
            architecture="x86_64",
            board="x86/64",
            system="Generic",
            version="1.0",
        ),
        logs=LogInfo(
            entries=[
                LogEntry(
                    raw="daemon.info netifd[1]: Interface 'wan' is now up",
                    timestamp=datetime.now(UTC).isoformat(),
                    facility="daemon",
                    priority="info",
                    ident="netifd",
                    message="Interface 'wan' is now up",
                )
            ]
        ),
        errors=[],
    )
    return snapshot
