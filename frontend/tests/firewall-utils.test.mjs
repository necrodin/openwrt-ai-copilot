// Firewall hardening regression tests.
//
// Exercise the real `lib/firewall-utils.ts` logic against the AC2350 shapes:
// the management endpoint dropping single-line UCI list options
// (`network='wan' 'wan6'`) and fw4 reporting "Usage:" instead of a version.
import test from "node:test";
import assert from "node:assert";

import { loadFirewallUtilsModule } from "./helpers.mjs";

const { isBogusVersion, sanitizeVersion, mergeZoneNetworks } =
  loadFirewallUtilsModule();

test("sanitizeVersion rejects fw4 usage output", () => {
  assert.strictEqual(isBogusVersion("Usage:"), true);
  assert.strictEqual(isBogusVersion("Usage:\n\n  /sbin/fw4 start|stop"), true);
  assert.strictEqual(isBogusVersion(null), true);
  assert.strictEqual(isBogusVersion(undefined), true);
  assert.strictEqual(isBogusVersion(""), true);
  assert.strictEqual(isBogusVersion("fw3 - v3.6.2"), false);
  assert.strictEqual(isBogusVersion("  fw4 1.0.1  "), false);
});

test("sanitizeVersion returns null for usage text, trimmed version otherwise", () => {
  assert.strictEqual(sanitizeVersion("Usage:"), null);
  assert.strictEqual(sanitizeVersion(null), null);
  assert.strictEqual(sanitizeVersion(undefined), null);
  assert.strictEqual(sanitizeVersion(""), null);
  assert.strictEqual(sanitizeVersion("  fw3 - v3.6.2  "), "fw3 - v3.6.2");
});

test("mergeZoneNetworks fills a dropped multi-network zone from the snapshot", () => {
  const managementZones = [
    { name: "lan", section: "@zone[0]", enabled: true, network: "lan" },
    // The management parser drops `network='wan' 'wan6'` -> null.
    { name: "wan", section: "@zone[1]", enabled: true, network: null },
  ];
  const snapshotZones = [
    { name: "lan", enabled: true, network: ["lan"], input: null, output: null, forward: null, masquerade: false, mtu_fix: false },
    { name: "wan", enabled: true, network: ["wan", "wan6"], input: "REJECT", output: "ACCEPT", forward: "DROP", masquerade: true, mtu_fix: true },
  ];
  const merged = mergeZoneNetworks(managementZones, snapshotZones);
  assert.strictEqual(merged[0].network, "lan"); // single-value string kept as-is
  assert.deepStrictEqual(merged[1].network, ["wan", "wan6"]);
});

test("mergeZoneNetworks leaves zones unchanged when networks are present", () => {
  const managementZones = [{ name: "guest", section: "@zone[0]", enabled: false, network: ["guest"] }];
  const merged = mergeZoneNetworks(managementZones, [
    { name: "guest", enabled: true, network: ["other"], input: null, output: null, forward: null, masquerade: false, mtu_fix: false },
  ]);
  assert.deepStrictEqual(merged[0].network, ["guest"]);
});

test("mergeZoneNetworks does not invent networks for unknown zones", () => {
  const managementZones = [{ name: "unknown", section: "@zone[9]", enabled: true, network: null }];
  const merged = mergeZoneNetworks(managementZones, [
    { name: "lan", enabled: true, network: ["lan"], input: null, output: null, forward: null, masquerade: false, mtu_fix: false },
  ]);
  assert.strictEqual(merged[0].network, null);
});
