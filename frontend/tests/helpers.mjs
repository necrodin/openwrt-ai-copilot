import path from "node:path";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);

// Next ships `jiti` as a transitive dependency; it is the only TypeScript
// loader available inside the frontend tree, so the regression tests borrow it
// to execute the real `lib/*.ts` modules (never a reimplementation).
const { createJiti } = require("jiti");
const jiti = createJiti(path.join(process.cwd(), "tests/loader.mjs"), {
  interopDefault: false,
  alias: { "@": process.cwd() },
});

export function loadClientsModule() {
  return jiti(path.join(process.cwd(), "lib/clients.ts"));
}

export function loadDashboardModule() {
  return jiti(path.join(process.cwd(), "lib/dashboard.ts"));
}

export function loadDashboardUtilsModule() {
  return jiti(path.join(process.cwd(), "lib/dashboard-utils.ts"));
}

export function loadDnsUtilsModule() {
  return jiti(path.join(process.cwd(), "lib/dns-utils.ts"));
}

/** A syntactically-complete `DeviceSnapshot` the TS logic can consume. */
export function makeSnapshot(overrides = {}) {
  return {
    meta: {
      collected_at: "2026-08-12T00:00:00Z",
      device_id: "test",
      transport: "ssh",
      host: "router",
      board: "test",
      model: "Test Router",
      firmware: "OpenWrt",
      collectors_run: [],
    },
    cpu: null,
    memory: null,
    temperature: [],
    storage: [],
    network: [],
    network_status: { gateway: null, dns: [], wan_interface: null },
    firewall: {
      defaults: null,
      zones: [],
      rules: [],
      forwards: [],
      nat: [],
      status: null,
      conntrack: null,
    },
    wifi: { radios: [], networks: [], clients: [] },
    clients: [],
    arp: [],
    neighbors: [],
    routing: [],
    vpn: [],
    dhcp: {
      pools: [],
      leases: [],
      static_leases: [],
      enabled: true,
      gateway: null,
      dns: [],
      domain: null,
    },
    packages: [],
    services: [],
    kernel: {
      kernel: "6.6.80",
      release: "OpenWrt",
      hostname: "router",
      model: "Test Router",
      architecture: "mips",
      board: "test",
      system: "",
      version: "1.0",
      distribution: null,
      release_version: null,
      revision: null,
      target: null,
      release_description: null,
      build_date: null,
    },
    logs: null,
    errors: [],
    ...overrides,
  };
}