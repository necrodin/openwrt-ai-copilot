// VPN tunnel-state regression tests.
//
// Exercise the real `lib/vpn-utils.ts` logic: a configured-but-not-running
// tunnel must never be shown as "Up"; configured / disabled / down are
// distinct states.
import test from "node:test";
import assert from "node:assert";

import { loadVpnUtilsModule } from "./helpers.mjs";

const { tunnelStatus } = loadVpnUtilsModule();

function tunnel(overrides = {}) {
  return {
    name: "tun0",
    kind: "openvpn",
    up: false,
    enabled: true,
    public_key: null,
    listen_port: null,
    endpoint: null,
    allowed_ips: [],
    addresses: [],
    peer_count: 0,
    rx_bytes: null,
    tx_bytes: null,
    version: null,
    uptime_seconds: null,
    detail: {},
    ...overrides,
  };
}

test("a running tunnel is Up", () => {
  assert.deepStrictEqual(tunnelStatus(tunnel({ up: true })), {
    label: "Up",
    tone: "success",
  });
});

test("a configured-but-inactive tunnel is Configured, never Up", () => {
  const status = tunnelStatus(
    tunnel({ up: false, enabled: true, detail: { state: "configured-but-inactive" } }),
  );
  assert.deepStrictEqual(status, { label: "Configured", tone: "warning" });
});

test("a disabled tunnel is Disabled", () => {
  assert.deepStrictEqual(
    tunnelStatus(tunnel({ up: false, enabled: false, detail: { state: "configured-but-inactive" } })),
    { label: "Disabled", tone: "neutral" },
  );
});

test("an unknown down tunnel is Down", () => {
  assert.deepStrictEqual(tunnelStatus(tunnel({ up: false, enabled: true })), {
    label: "Down",
    tone: "neutral",
  });
});
