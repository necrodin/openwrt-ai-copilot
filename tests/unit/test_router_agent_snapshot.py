"""Snapshot assembly tests: ONE normalized JSON, error containment."""

from __future__ import annotations

import json

from router_agent.collectors import COLLECTOR_NAMES, select_collectors
from router_agent.config import AgentConfig
from router_agent.errors import CommandError
from router_agent.model import DeviceSnapshot
from router_agent.snapshot import build_snapshot
from tests.unit.router_agent_helpers import make_context

FULL_SCRIPTS = {
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
    ),
    "ubus call system info": json.dumps(
        {"load_1": 0.25, "load_5": 0.2, "load_15": 0.1, "uptime": 3600}
    ),
    "cat /proc/cpuinfo": "processor : 0\nprocessor : 1\n",
    "cat /proc/meminfo": (
        "MemTotal:       1000000 kB\nMemFree:        500000 kB\n"
        "Buffers:         30000 kB\nCached:          40000 kB\nMemAvailable:   600000 kB\n"
    ),
    "ls /sys/class/thermal/": "thermal_zone0\n",
    "cat /sys/class/thermal/thermal_zone0/temp": "45000",
    "cat /sys/class/thermal/thermal_zone0/type": "cpu",
    "df -kP": "Filesystem     1024-blocks      Used Available Capacity Mounted on\n"
    "ubi0:rootfs       32768     10000     22000      31% /\n",
    "ubus call network.interface dump": json.dumps(
        {
            "interface": [
                {
                    "interface": "lan",
                    "up": True,
                    "proto": "static",
                    "device": "br-lan",
                    "addresses": [{"address": "192.168.1.1", "mask": 24}],
                }
            ]
        }
    ),
    "ubus call network.device status": json.dumps(
        {
            "device": {
                "br-lan": {
                    "up": True,
                    "link": True,
                    "speed": 100,
                    "macaddress": "aa:bb:cc:dd:ee:ff",
                    "statistics": {"rx_bytes": 1, "tx_bytes": 2},
                }
            }
        }
    ),
    "uci show firewall": "firewall.@zone[0]=zone\nfirewall.@zone[0].name='lan'\n"
    "firewall.@zone[0].input='ACCEPT'\n",
    "ubus call wifi status": json.dumps(
        {
            "radio0": {
                "up": True,
                "config": {"hwmode": "11n", "channel": "1", "frequency": "2412"},
                "interfaces": [{"config": {"ssid": "Home"}}],
                "stations": {"11:22:33:44:55:66": {"signal": -45}},
            }
        }
    ),
    "ubus call dhcp leases": json.dumps(
        {"leases": [{"hostname": "pc", "ip": "192.168.1.50", "mac": "aa:bb:cc:00:00:01"}]}
    ),
    "cat /proc/net/arp": (
        "IP address       HW type     Flags       HW address            Mask     Device\n"
        "192.168.1.50     0x1         0x2         aa:bb:cc:00:00:01     *        br-lan\n"
    ),
    "ip -o route show": "default via 192.168.1.1 dev eth0 proto static metric 100\n",
    "ip -o -6 route show": "",
    "wg show all interfaces": "wg0:\tpublic-key: PUB\nwg0:\tlisten-port: 51820\n",
    "uci show openvpn": "",
    "uci show dhcp": "dhcp.@dhcp[0]=dhcp\ndhcp.@dhcp[0].interface='lan'\n"
    "dhcp.@dhcp[0].start='100'\ndhcp.@dhcp[0].limit='150'\n",
    "opkg list-installed": "base-files - 258 - Base\n",
    "logread -l 200": "Mon Aug  1 23:04:41 2026 daemon.info hostapd[1]: hello\n",
}


def test_snapshot_one_normalized_json() -> None:
    ctx = make_context(FULL_SCRIPTS)
    config = ctx.config
    snapshot = build_snapshot(
        ctx,
        select_collectors(config),
        device_id="dev-1",
        transport="ssh",
        host="192.168.1.1",
    )

    assert isinstance(snapshot, DeviceSnapshot)
    data = snapshot.model_dump()

    assert data["meta"]["device_id"] == "dev-1"
    assert data["meta"]["host"] == "192.168.1.1"
    assert data["meta"]["board"] == "x86/64"
    assert data["meta"]["firmware"] == "SNAPSHOT"
    assert data["meta"]["collectors_run"] == list(COLLECTOR_NAMES)
    assert len(data["meta"]["collectors_run"]) == 15
    assert data["errors"] == []

    assert data["cpu"]["load_1"] == 0.25
    assert data["cpu"]["cores"] == 2
    assert data["memory"]["total_kb"] == 1000000
    assert data["temperature"][0]["temperature_c"] == 45.0
    assert data["storage"][0]["mountpoint"] == "/"
    assert data["network"][0]["name"] == "lan"
    assert data["network"][0]["addresses"][0]["address"] == "192.168.1.1"
    assert data["firewall"]["zones"][0]["name"] == "lan"
    assert data["wifi"]["radios"][0]["ssid"] == "Home"
    assert data["wifi"]["clients"][0]["mac"] == "11:22:33:44:55:66"
    assert data["clients"][0]["ip"] == "192.168.1.50"
    assert data["arp"][0]["ip"] == "192.168.1.50"
    assert data["routing"][0]["gateway"] == "192.168.1.1"
    assert data["vpn"][0]["kind"] == "wireguard"
    assert data["dhcp"]["pools"][0]["limit"] == 150
    assert data["packages"][0]["name"] == "base-files"
    assert data["kernel"]["kernel"] == "6.6.80"
    assert data["logs"]["entries"][0]["message"] == "hello"


def test_snapshot_contains_errors_without_aborting() -> None:
    from router_agent.collectors.base import Collector
    from router_agent.collectors.cpu import CpuCollector

    class BrokenCollector(Collector):
        name = "broken"

        def collect(self, ctx):
            raise CommandError("boom")

    ctx = make_context(
        {
            "ubus call system board": json.dumps(
                {"hostname": "OpenWrt", "kernel": "6.6.80", "release": "SNAPSHOT"}
            )
        }
    )
    snapshot = build_snapshot(
        ctx,
        [CpuCollector(), BrokenCollector()],
        device_id="dev-1",
        transport="local",
        host="",
    )
    # The broken collector is recorded but the rest of the snapshot still builds.
    assert snapshot.cpu is not None
    assert [e.collector for e in snapshot.errors] == ["broken"]
    assert snapshot.kernel.kernel == "6.6.80"


def test_snapshot_uses_configured_subset() -> None:
    config = AgentConfig(enabled_collectors={"cpu", "kernel"})
    ctx = make_context(
        {
            "ubus call system board": json.dumps({"hostname": "r1", "kernel": "5.10"}),
            "ubus call system info": json.dumps({"load_1": 1.0, "uptime": 10}),
        }
    )
    snapshot = build_snapshot(
        ctx, select_collectors(config), device_id="dev-1", transport="ssh", host="r1"
    )
    assert snapshot.cpu is not None
    assert snapshot.memory is None
    assert snapshot.meta.collectors_run == ["cpu", "kernel"]


def test_fake_runner_is_lenient_via_sh() -> None:
    from router_agent.collectors.storage import StorageCollector

    ctx = make_context({})
    # ctx.sh swallows failures and returns the default, so a collector yields an
    # empty (but valid) section instead of raising.
    assert StorageCollector().collect(ctx) == []
