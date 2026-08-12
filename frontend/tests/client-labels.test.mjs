// Persistent device-label regression tests.
//
// Exercise the real `lib/clients.ts` logic under Node's built-in test runner:
// MAC normalization, label merge by MAC, search matching, and persistence of a
// label when a device's IP changes.
import test from "node:test";
import assert from "node:assert";

import { loadClientsModule, makeSnapshot } from "./helpers.mjs";

const {
  buildClients,
  applyClientLabels,
  canonicalizeMac,
  filterClients,
} = loadClientsModule();

function snapshotWithClients(overrides = {}) {
  return makeSnapshot({
    arp: [
      { ip: "192.168.100.21", mac: "aa:bb:cc:11:22:33", interface: "br-lan", state: "complete" },
      { ip: "192.168.100.58", mac: "dd:ee:ff:44:55:66", interface: "br-lan", state: "complete" },
      { ip: "192.168.100.77", mac: "aa:bb:cc:00:00:99", interface: "br-lan", state: "complete" },
    ],
    ...overrides,
  });
}

function build(snapshot, nowIso = "2026-08-12T00:00:00Z") {
  return buildClients(snapshot, nowIso);
}

test("canonicalizeMac maps equivalent representations to one key", () => {
  assert.strictEqual(canonicalizeMac("AA:BB:CC:11:22:33"), "aa:bb:cc:11:22:33");
  assert.strictEqual(canonicalizeMac("AA-BB-CC-11-22-33"), "aa:bb:cc:11:22:33");
  assert.strictEqual(canonicalizeMac("AABBCC112233"), "aa:bb:cc:11:22:33");
  assert.strictEqual(canonicalizeMac("aa:bb:cc:11:22:33"), "aa:bb:cc:11:22:33");
  assert.strictEqual(canonicalizeMac(null), null);
  assert.strictEqual(canonicalizeMac("not-a-mac"), null);
  assert.strictEqual(canonicalizeMac("aa:bb:cc:11:22"), null);
});

test("label is merged into the client response by MAC", () => {
  const clients = build(snapshotWithClients());
  const labeled = applyClientLabels(clients, [
    { mac_address: "aa:bb:cc:11:22:33", label: "Talat iPhone", created_at: null, updated_at: null },
  ]);
  const phone = labeled.find((client) => client.mac === "aa:bb:cc:11:22:33");
  assert.strictEqual(phone.label, "Talat iPhone");
  // Existing client fields are preserved, never replaced.
  assert.strictEqual(phone.ipv4, "192.168.100.21");
  assert.strictEqual(phone.mac, "aa:bb:cc:11:22:33");
  assert.strictEqual(phone.online, true);
  assert.strictEqual(phone.hostname, null);
});

test("unlabeled client remains unchanged", () => {
  const clients = build(snapshotWithClients());
  const labeled = applyClientLabels(clients, [
    { mac_address: "aa:bb:cc:11:22:33", label: "Talat iPhone", created_at: null, updated_at: null },
  ]);
  const other = labeled.find((client) => client.mac === "dd:ee:ff:44:55:66");
  assert.strictEqual(other.label, undefined);
  assert.strictEqual(other.ipv4, "192.168.100.58");
});

test("equivalent MAC representations map to the same label", () => {
  const clients = build(snapshotWithClients());
  const labeled = applyClientLabels(clients, [
    { mac_address: "AA:BB:CC:11:22:33", label: "Salon TV", created_at: null, updated_at: null },
  ]);
  const tv = labeled.find((client) => client.mac === "aa:bb:cc:11:22:33");
  assert.strictEqual(tv.label, "Salon TV");
});

test("search matches the label", () => {
  const clients = build(snapshotWithClients());
  const labeled = applyClientLabels(clients, [
    { mac_address: "aa:bb:cc:11:22:33", label: "Talat iPhone", created_at: null, updated_at: null },
  ]);
  const results = filterClients(labeled, {
    search: "iphone",
    connection: "all",
    medium: "all",
  });
  assert.strictEqual(results.length, 1);
  assert.strictEqual(results[0].mac, "aa:bb:cc:11:22:33");
});

test("label persists when the device IP changes", () => {
  // Same MAC on a new IP — the label must survive because identity is MAC-based.
  const clients = build(
    snapshotWithClients({
      arp: [
        { ip: "192.168.100.58", mac: "aa:bb:cc:11:22:33", interface: "br-lan", state: "complete" },
      ],
    }),
  );
  const labeled = applyClientLabels(clients, [
    { mac_address: "aa:bb:cc:11:22:33", label: "Talat iPhone", created_at: null, updated_at: null },
  ]);
  const phone = labeled.find((client) => client.mac === "aa:bb:cc:11:22:33");
  assert.strictEqual(phone.ipv4, "192.168.100.58");
  assert.strictEqual(phone.label, "Talat iPhone");
});

test("a label update replaces the old label for the same MAC", () => {
  const clients = build(snapshotWithClients());
  const first = applyClientLabels(clients, [
    { mac_address: "aa:bb:cc:11:22:33", label: "Old name", created_at: null, updated_at: null },
  ]);
  const updated = applyClientLabels(first, [
    { mac_address: "aa:bb:cc:11:22:33", label: "New name", created_at: null, updated_at: null },
  ]);
  const phone = updated.find((client) => client.mac === "aa:bb:cc:11:22:33");
  assert.strictEqual(phone.label, "New name");
});
