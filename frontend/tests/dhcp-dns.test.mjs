// DHCP lease expiry + DNS resolver reconciliation regression tests.
//
// Exercise the real `lib/dashboard-utils.ts` lease helpers and `lib/dns-utils.ts`
// resolver reconciliation against the AC2350-shaped data (epoch lease expiry,
// resolv.conf showing only the local stub, netifd upstream in the snapshot).
import test from "node:test";
import assert from "node:assert";

import { loadDashboardUtilsModule, loadDnsUtilsModule } from "./helpers.mjs";

const { leaseExpirySeconds, formatLeaseExpiry, activeLeaseCount } =
  loadDashboardUtilsModule();
const {
  reconcileUpstream,
  isLoopbackResolver,
  filterInternalHosts,
  dedupeResolvers,
} = loadDnsUtilsModule();

test("leaseExpirySeconds parses dnsmasq epoch and rejects junk", () => {
  assert.strictEqual(leaseExpirySeconds("1786600513"), 1786600513);
  assert.strictEqual(leaseExpirySeconds(1786600513), 1786600513);
  assert.strictEqual(leaseExpirySeconds(null), null);
  assert.strictEqual(leaseExpirySeconds(undefined), null);
  assert.strictEqual(leaseExpirySeconds("not-a-number"), null);
});

test("formatLeaseExpiry renders a readable timestamp, never a raw epoch", () => {
  const rendered = formatLeaseExpiry("1786600513");
  assert.ok(rendered && rendered.length > 0);
  assert.ok(!rendered.includes("1786600513"));
  assert.strictEqual(formatLeaseExpiry(null), null);
  assert.strictEqual(formatLeaseExpiry("junk"), null);
});

test("activeLeaseCount counts only unexpired leases", () => {
  const nowSeconds = 1_800_000_000;
  const nowMs = nowSeconds * 1000;
  const leases = [
    { ip: "192.168.100.21", expires: String(nowSeconds + 5000) }, // active
    { ip: "192.168.100.58", expires: String(nowSeconds - 5000) }, // expired
    { ip: "192.168.100.99", expires: null }, // unknown expiry -> assumed active
  ];
  assert.strictEqual(activeLeaseCount(leases, nowMs), 2);
});

test("isLoopbackResolver flags the local stub", () => {
  assert.strictEqual(isLoopbackResolver("127.0.0.1"), true);
  assert.strictEqual(isLoopbackResolver("::1"), true);
  assert.strictEqual(isLoopbackResolver("localhost"), true);
  assert.strictEqual(isLoopbackResolver("192.168.1.1"), false);
  assert.strictEqual(isLoopbackResolver("8.8.8.8"), false);
  assert.strictEqual(isLoopbackResolver("fe80::2aa:bbff:fe01:2340"), false);
});

test("reconcileUpstream uses snapshot DNS as the authoritative upstream", () => {
  // AC2350 shape: resolv.conf only has the local stub; the snapshot carries
  // the real netifd resolvers.
  const managementUpstream = ["127.0.0.1", "::1"];
  const snapshotDns = ["192.168.1.1", "fe80::2aa:bbff:fe01:2340"];
  assert.deepStrictEqual(reconcileUpstream(managementUpstream, snapshotDns), [
    "192.168.1.1",
    "fe80::2aa:bbff:fe01:2340",
  ]);
});

test("reconcileUpstream never surfaces the local stub as upstream", () => {
  assert.deepStrictEqual(reconcileUpstream(["127.0.0.1", "::1"], []), []);
  assert.deepStrictEqual(reconcileUpstream([], ["192.168.1.1"]), ["192.168.1.1"]);
});

test("reconcileUpstream deduplicates IPv4 and IPv6 resolvers", () => {
  const result = reconcileUpstream([], [
    "192.168.1.1",
    "192.168.1.1",
    "fe80::1",
    "192.168.1.1",
  ]);
  assert.deepStrictEqual(result, ["192.168.1.1", "fe80::1"]);
});

test("reconcileUpstream handles empty/unavailable DNS", () => {
  assert.deepStrictEqual(reconcileUpstream([], []), []);
  assert.deepStrictEqual(reconcileUpstream([], null), []);
  assert.deepStrictEqual(reconcileUpstream([], undefined), []);
});

test("dedupeResolvers drops duplicates preserving order", () => {
  assert.deepStrictEqual(dedupeResolvers(["a", "a", "b", "c", "b"]), ["a", "b", "c"]);
  assert.deepStrictEqual(dedupeResolvers(["", " a ", "a"]), ["a"]);
});

test("filterInternalHosts drops loopback/multicast, keeps real hosts", () => {
  const hosts = [
    { ip: "127.0.0.1", hostname: "localhost" },
    { ip: "::1", hostname: "localhost" },
    { ip: "ff02::1", hostname: "ip6-allnodes" },
    { ip: "192.168.100.5", hostname: "nas" },
    { ip: "10.0.0.2", hostname: "printer" },
  ];
  const filtered = filterInternalHosts(hosts);
  assert.deepStrictEqual(filtered, [
    { ip: "192.168.100.5", hostname: "nas" },
    { ip: "10.0.0.2", hostname: "printer" },
  ]);
});
