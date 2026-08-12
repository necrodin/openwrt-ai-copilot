// LAN connected-client count regression tests.
//
// These exercise the real `lib/clients.ts` `countOnlineLanClients` logic under
// Node's built-in test runner (no extra tooling): load the TypeScript module
// through Next's `jiti` and assert against fixture snapshots.
import test from "node:test";
import assert from "node:assert";

import { loadClientsModule, makeSnapshot } from "./helpers.mjs";

const { countOnlineLanClients } = loadClientsModule();

function lanSnapshot(overrides = {}) {
  return makeSnapshot({
    network_status: {
      gateway: "192.168.1.1",
      dns: ["192.168.1.1"],
      wan_interface: "eth0.2",
    },
    network: [
      {
        name: "lan",
        up: true,
        proto: "static",
        device: "br-lan",
        mac: "aa:bb:cc:dd:ee:ff",
        link: true,
        speed_mbps: 1000,
        mtu: 1500,
        rx_bytes: null,
        tx_bytes: null,
        is_bridge: true,
        vlan_id: null,
        gateway: null,
        addresses: [{ address: "192.168.31.1", prefix: 24, family: "ipv4", is_public: false }],
        bridge_members: ["eth0.1", "phy0-ap0", "phy1-ap0"],
        stp_enabled: false,
        forward_delay: 8,
        uptime_seconds: null,
        rx_errors: null,
        tx_errors: null,
        rx_dropped: null,
        tx_dropped: null,
      },
      {
        name: "wan",
        up: true,
        proto: "dhcp",
        device: "eth0.2",
        mac: "aa:bb:cc:dd:ee:01",
        link: true,
        speed_mbps: 1000,
        mtu: 1500,
        rx_bytes: null,
        tx_bytes: null,
        is_bridge: false,
        vlan_id: null,
        gateway: "192.168.1.1",
        addresses: [{ address: "192.168.1.121", prefix: 24, family: "ipv4", is_public: false }],
        bridge_members: [],
        stp_enabled: null,
        forward_delay: null,
        uptime_seconds: null,
        rx_errors: null,
        tx_errors: null,
        rx_dropped: null,
        tx_dropped: null,
      },
    ],
    ...overrides,
  });
}

test("counts online LAN clients from ARP + DHCP", () => {
  const snapshot = lanSnapshot({
    arp: [
      { ip: "192.168.31.50", mac: "aa:bb:cc:dd:ee:02", interface: "br-lan", state: "complete" },
      { ip: "192.168.31.51", mac: "aa:bb:cc:dd:ee:03", interface: "br-lan", state: "complete" },
    ],
    clients: [
      { hostname: "desktop", ip: "192.168.31.50", mac: "aa:bb:cc:dd:ee:02", expires: null, interface: "br-lan" },
    ],
  });
  assert.strictEqual(countOnlineLanClients(snapshot, "2026-08-12T00:00:00Z"), 2);
});

test("counts a wireless client attached through the LAN bridge", () => {
  const snapshot = lanSnapshot({
    wifi: {
      radios: [],
      networks: [],
      clients: [{ mac: "11:22:33:44:55:66", ssid: "Home", interface: "phy0-ap0" }],
    },
    arp: [
      { ip: "192.168.31.60", mac: "11:22:33:44:55:66", interface: "phy0-ap0", state: "complete" },
    ],
  });
  assert.strictEqual(countOnlineLanClients(snapshot, "2026-08-12T00:00:00Z"), 1);
});

test("does not count WAN-side clients", () => {
  const snapshot = lanSnapshot({
    arp: [
      // WAN-side network (192.168.1.0/24): upstream router + ISP host
      { ip: "192.168.1.1", mac: "00:11:22:33:44:55", interface: "eth0.2", state: "complete" },
      { ip: "192.168.1.121", mac: "00:11:22:33:44:56", interface: "eth0.2", state: "complete" },
      // a genuinely local host on the LAN bridge
      { ip: "192.168.31.70", mac: "aa:bb:cc:dd:ee:04", interface: "br-lan", state: "complete" },
    ],
  });
  assert.strictEqual(countOnlineLanClients(snapshot, "2026-08-12T00:00:00Z"), 1);
});

test("unknown when no online signal is present", () => {
  // DHCP leases exist but no ARP table and no WiFi stations: we cannot tell
  // which are online right now -> Unknown (null), not a guessed number.
  const snapshot = lanSnapshot({
    clients: [{ hostname: "tv", ip: "192.168.31.80", mac: "aa:bb:cc:dd:ee:05", expires: null, interface: "br-lan" }],
  });
  assert.strictEqual(countOnlineLanClients(snapshot, "2026-08-12T00:00:00Z"), null);
});

test("null snapshot -> Unknown", () => {
  assert.strictEqual(countOnlineLanClients(null, "2026-08-12T00:00:00Z"), null);
});

test("no clients at all -> 0", () => {
  const snapshot = lanSnapshot({ network: [] });
  assert.strictEqual(countOnlineLanClients(snapshot, "2026-08-12T00:00:00Z"), 0);
});