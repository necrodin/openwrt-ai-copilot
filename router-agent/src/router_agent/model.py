"""Normalized, provider- and transport-independent device snapshot model.

Every collector emits one of these section models; the snapshot assembles them
into a single :class:`DeviceSnapshot`. This is the *only* shape the router agent
produces, regardless of whether data came over SSH, local execution, or LuCI
RPC. Field names are stable and documented — downstream consumers (diagnostics,
fleet telemetry) depend on them.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

# --------------------------------------------------------------------------- #
# Sections                                                                     #
# --------------------------------------------------------------------------- #


class CpuInfo(BaseModel):
    load_1: float
    load_5: float
    load_15: float
    cores: int = 1
    uptime_seconds: float = 0.0
    usage_percent: float | None = None
    frequency_mhz: int | None = None
    model: str | None = None
    architecture: str | None = None
    temperature_c: float | None = None


class MemoryInfo(BaseModel):
    total_kb: int
    free_kb: int
    used_kb: int
    buffered_kb: int = 0
    cached_kb: int | None = None
    available_kb: int | None = None
    swap_total_kb: int | None = None
    swap_free_kb: int | None = None
    swap_used_kb: int | None = None


class TemperatureReading(BaseModel):
    zone: str
    temperature_c: float


class StorageMount(BaseModel):
    device: str
    mountpoint: str
    filesystem: str = ""
    total_bytes: int | None = None
    used_bytes: int | None = None
    available_bytes: int | None = None
    use_percent: float | None = None
    inodes_total: int | None = None
    inodes_used: int | None = None
    inodes_available: int | None = None
    inode_use_percent: float | None = None
    #: Flash wear level (erase count) when the device reports it (e.g. UBI).
    wear: int | None = None
    #: Best-effort media health string ("ok" / "degraded" / "unknown").
    health: str | None = None


class NetworkAddress(BaseModel):
    address: str
    prefix: int = 0
    family: Literal["ipv4", "ipv6"]


class NetworkInterface(BaseModel):
    name: str
    up: bool = False
    proto: str | None = None
    device: str | None = None
    mac: str | None = None
    link: bool | None = None
    speed_mbps: int | None = None
    mtu: int | None = None
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    is_bridge: bool = False
    vlan_id: int | None = None
    gateway: str | None = None
    addresses: list[NetworkAddress] = Field(default_factory=list)
    bridge_members: list[str] = Field(default_factory=list)
    stp_enabled: bool | None = None
    forward_delay: int | None = None
    #: Best-effort connection uptime in seconds when netifd reports it.
    uptime_seconds: int | None = None
    rx_errors: int | None = None
    tx_errors: int | None = None
    rx_dropped: int | None = None
    tx_dropped: int | None = None


#: Interface protos that identify a WAN/uplink regardless of the interface name
#: (``wan``, ``eth0.2``, or a cellular modem). Shared by collectors, diagnostics
#: and the frontend so WAN detection stays consistent across layers.
WAN_PROTOS: frozenset[str] = frozenset(
    {"dhcp", "dhcpv6", "pppoe", "ppp", "qmi", "wwan", "wwan6", "3g", "lte"}
)


class NetworkStatus(BaseModel):
    """Network-wide state: default gateway and configured DNS servers."""

    gateway: str | None = None
    dns: list[str] = Field(default_factory=list)
    wan_interface: str | None = None


class FirewallZone(BaseModel):
    name: str
    input: str | None = None
    output: str | None = None
    forward: str | None = None
    masquerade: bool = False
    network: list[str] = Field(default_factory=list)
    mtu_fix: bool = False


class FirewallRule(BaseModel):
    name: str = ""
    src: str | None = None
    dest: str | None = None
    proto: str | None = None
    target: str | None = None
    family: str | None = None
    src_port: str | None = None
    dest_port: str | None = None
    enabled: bool = True
    section: str | None = None


class FirewallForward(BaseModel):
    """A port-forward (UCI ``redirect`` section)."""

    name: str = ""
    proto: str | None = None
    src: str | None = None
    src_dport: str | None = None
    src_ip: str | None = None
    dest: str | None = None
    dest_ip: str | None = None
    dest_port: str | None = None
    target: str | None = None
    enabled: bool = True
    section: str | None = None


class FirewallNat(BaseModel):
    """A NAT definition (UCI ``nat`` section)."""

    name: str = ""
    target: str | None = None
    family: str | None = None
    src: str | None = None
    src_dport: str | None = None
    dest: str | None = None
    dest_ip: str | None = None
    dest_port: str | None = None
    proto: str | None = None
    enabled: bool = True
    section: str | None = None


class FirewallDefaults(BaseModel):
    """Default zone policies and protection switches."""

    input: str | None = None
    output: str | None = None
    forward: str | None = None
    masquerade: bool = False
    syn_flood: bool = False
    osf: bool = False
    mtu: int | None = None


class FirewallStatus(BaseModel):
    """Runtime state and identity of the firewall service."""

    running: bool = False
    enabled: bool = False
    version: str | None = None


class FirewallConntrack(BaseModel):
    """Current connection-tracking utilization."""

    count: int | None = None
    max: int | None = None


class FirewallInfo(BaseModel):
    zones: list[FirewallZone] = Field(default_factory=list)
    rules: list[FirewallRule] = Field(default_factory=list)
    forwards: list[FirewallForward] = Field(default_factory=list)
    nat: list[FirewallNat] = Field(default_factory=list)
    defaults: FirewallDefaults = Field(default_factory=FirewallDefaults)
    status: FirewallStatus = Field(default_factory=FirewallStatus)
    conntrack: FirewallConntrack | None = None


class WifiRadio(BaseModel):
    name: str
    up: bool = False
    mode: str | None = None
    band: str | None = None
    channel: int | None = None
    frequency_mhz: int | None = None
    tx_power: int | None = None
    ssid: str | None = None
    hwmode: str | None = None
    width_mhz: int | None = None
    station_count: int = 0
    #: Regulatory country code from the UCI radio config (e.g. ``US``).
    country: str | None = None
    #: Hardware identifier (e.g. the ACPI/platform path the radio is on).
    hardware: str | None = None


class WifiNetwork(BaseModel):
    """A configured wireless network (SSID / ``wifi-iface`` section)."""

    ssid: str
    radio: str
    interface: str | None = None
    mode: str | None = None
    encryption: str | None = None
    hidden: bool = False
    enabled: bool = True
    network: str | None = None
    client_count: int = 0
    section: str = ""


class WifiClient(BaseModel):
    mac: str
    ssid: str | None = None
    signal_dbm: int | None = None
    tx_bytes: int | None = None
    rx_bytes: int | None = None
    connected_minutes: int | None = None
    #: Station signal-to-noise ratio and bitrates as reported by hostapd.
    noise: int | None = None
    rx_rate: int | None = None
    tx_rate: int | None = None
    interface: str | None = None
    #: Association age in seconds.
    connected_time: int | None = None


class WifiInfo(BaseModel):
    radios: list[WifiRadio] = Field(default_factory=list)
    networks: list[WifiNetwork] = Field(default_factory=list)
    clients: list[WifiClient] = Field(default_factory=list)


class ArpEntry(BaseModel):
    ip: str
    mac: str
    interface: str
    state: str = "unknown"


class NeighborEntry(BaseModel):
    """One entry in the IPv6 neighbor discovery cache (MAC &rarr; IPv6).

    Unlike the ARP table (IPv4 &rarr; MAC), this maps a link-layer address to its
    IPv6 addresses so a client can be resolved across address families.
    """

    ip: str
    mac: str | None = None
    interface: str | None = None
    state: str | None = None
    family: Literal["ipv6", "ipv4"] = "ipv6"


class RouteEntry(BaseModel):
    destination: str
    gateway: str | None = None
    interface: str | None = None
    metric: int | None = None
    family: Literal["ipv4", "ipv6"]
    flags: str = ""


class VpnTunnel(BaseModel):
    """A VPN tunnel or service detected on the router.

    ``kind`` distinguishes the technology so consumers can render the right
    details; ``detail`` carries technology-specific runtime data (peers, routes,
    daemon state) whose shape follows the kind. Everything is best-effort and
    absent technologies simply never produce an entry.
    """

    name: str
    kind: Literal["wireguard", "openvpn", "ipsec", "tailscale", "zerotier", "other"]
    up: bool = False
    enabled: bool = True
    public_key: str | None = None
    listen_port: int | None = None
    endpoint: str | None = None
    allowed_ips: list[str] = Field(default_factory=list)
    addresses: list[str] = Field(default_factory=list)
    peer_count: int = 0
    rx_bytes: int | None = None
    tx_bytes: int | None = None
    version: str | None = None
    uptime_seconds: int | None = None
    detail: dict = Field(default_factory=dict)


class DhcpPool(BaseModel):
    name: str
    interface: str | None = None
    start: str | None = None
    limit: int | None = None
    leasetime: str | None = None
    range_end: str | None = None


class DhcpStaticLease(BaseModel):
    """A UCI ``dhcp.@host`` static lease (MAC → fixed IP)."""

    section: str
    hostname: str | None = None
    ip: str | None = None
    mac: str | None = None
    enabled: bool = True


class DhcpLease(BaseModel):
    hostname: str = ""
    ip: str
    mac: str | None = None
    expires: str | None = None
    interface: str | None = None


class DhcpInfo(BaseModel):
    pools: list[DhcpPool] = Field(default_factory=list)
    leases: list[DhcpLease] = Field(default_factory=list)
    static_leases: list[DhcpStaticLease] = Field(default_factory=list)
    enabled: bool = True
    gateway: str | None = None
    dns: list[str] = Field(default_factory=list)
    domain: str | None = None


class Package(BaseModel):
    name: str
    version: str = ""
    description: str = ""


class KernelInfo(BaseModel):
    kernel: str = ""
    release: str = ""
    hostname: str = ""
    model: str = ""
    architecture: str = ""
    board: str = ""
    system: str = ""
    version: str = ""
    #: Structured OpenWrt release details parsed from the ``release`` field of
    #: ``ubus system board`` (a dict on modern OpenWrt, a string on older ones).
    #: ``release`` above stays a clean human-readable string; these fields carry
    #: the individual components so UIs never render a raw dict.
    distribution: str | None = None
    release_version: str | None = None
    revision: str | None = None
    target: str | None = None
    release_description: str | None = None
    #: Build date when the release metadata reports one (may be absent).
    build_date: str | None = None


class LogEntry(BaseModel):
    raw: str
    timestamp: str | None = None
    facility: str | None = None
    priority: str | None = None
    ident: str | None = None
    message: str = ""


class LogInfo(BaseModel):
    entries: list[LogEntry] = Field(default_factory=list)


class ServiceInfo(BaseModel):
    """A system service detected on the router with its health signals."""

    name: str
    running: bool = False
    enabled: bool = False
    configured: bool = False
    version: str | None = None
    detail: str | None = None


# --------------------------------------------------------------------------- #
# Snapshot                                                                    #
# --------------------------------------------------------------------------- #


class SnapshotMeta(BaseModel):
    collected_at: datetime
    device_id: str = "unconfigured"
    transport: str = "unknown"
    host: str = ""
    board: str = ""
    model: str = ""
    firmware: str = ""
    collectors_run: list[str] = Field(default_factory=list)


class CollectError(BaseModel):
    collector: str
    error: str


class DeviceSnapshot(BaseModel):
    """One normalized JSON document describing the router's current state."""

    meta: SnapshotMeta
    cpu: CpuInfo | None = None
    memory: MemoryInfo | None = None
    temperature: list[TemperatureReading] = Field(default_factory=list)
    storage: list[StorageMount] = Field(default_factory=list)
    network: list[NetworkInterface] = Field(default_factory=list)
    network_status: NetworkStatus | None = None
    firewall: FirewallInfo = Field(default_factory=FirewallInfo)
    wifi: WifiInfo = Field(default_factory=WifiInfo)
    clients: list[DhcpLease] = Field(default_factory=list)
    arp: list[ArpEntry] = Field(default_factory=list)
    neighbors: list[NeighborEntry] = Field(default_factory=list)
    routing: list[RouteEntry] = Field(default_factory=list)
    vpn: list[VpnTunnel] = Field(default_factory=list)
    dhcp: DhcpInfo = Field(default_factory=DhcpInfo)
    packages: list[Package] = Field(default_factory=list)
    services: list[ServiceInfo] = Field(default_factory=list)
    kernel: KernelInfo = Field(default_factory=KernelInfo)
    logs: LogInfo = Field(default_factory=LogInfo)
    errors: list[CollectError] = Field(default_factory=list)


__all__ = [
    "ArpEntry",
    "CollectError",
    "CpuInfo",
    "DeviceSnapshot",
    "DhcpInfo",
    "DhcpLease",
    "DhcpPool",
    "DhcpStaticLease",
    "FirewallConntrack",
    "FirewallDefaults",
    "FirewallForward",
    "FirewallInfo",
    "FirewallNat",
    "FirewallRule",
    "FirewallStatus",
    "FirewallZone",
    "KernelInfo",
    "LogEntry",
    "LogInfo",
    "MemoryInfo",
    "NeighborEntry",
    "NetworkAddress",
    "NetworkInterface",
    "NetworkStatus",
    "Package",
    "RouteEntry",
    "ServiceInfo",
    "SnapshotMeta",
    "StorageMount",
    "TemperatureReading",
    "VpnTunnel",
    "WifiClient",
    "WifiInfo",
    "WifiNetwork",
    "WifiRadio",
]
