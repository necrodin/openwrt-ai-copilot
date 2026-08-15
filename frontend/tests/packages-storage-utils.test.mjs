// Packages + Storage hardening regression tests.
//
// Exercise the real `lib/packages-utils.ts` and `lib/storage-utils.ts` logic
// against the AC2350 shapes: repository-unavailable vs no-match search results,
// read-only squashfs /rom mounts, and `df` header artifacts.
import test from "node:test";
import assert from "node:assert";

import { loadPackagesUtilsModule, loadStorageUtilsModule } from "./helpers.mjs";

const { searchEmptyState } = loadPackagesUtilsModule();
const {
  isReadonlyFirmwareMount,
  isBogusMount,
  usableMounts,
  mountUsageTone,
} = loadStorageUtilsModule();

function mount(overrides = {}) {
  return {
    device: "/dev/root",
    mountpoint: "/rom",
    filesystem: "squashfs",
    options: "ro,noatime",
    total_bytes: 4864 * 1024,
    used_bytes: 4864 * 1024,
    available_bytes: 0,
    use_percent: 100,
    overlay: false,
    rootfs: false,
    ...overrides,
  };
}

// -- packages: search empty-state ------------------------------------------ //

test("empty search with repository available is a no-match", () => {
  const state = searchEmptyState({
    query: "nope",
    manager: "apk",
    count: 0,
    results: [],
    repository: { available: true },
  });
  assert.strictEqual(state.kind, "no-match");
  assert.match(state.title, /No packages match/);
});

test("empty search with unavailable repository is repository-unavailable", () => {
  const state = searchEmptyState({
    query: "luci",
    manager: "apk",
    count: 0,
    results: [],
    repository: {
      available: false,
      reason: "The package repository database is unavailable on the router.",
      detail: ["WARNING: opening from cache ... No such file or directory"],
    },
  });
  assert.strictEqual(state.kind, "repository-unavailable");
  assert.match(state.title, /repository is unavailable/);
  assert.ok(state.reason && state.reason.length > 0);
  assert.deepStrictEqual(state.detail, [
    "WARNING: opening from cache ... No such file or directory",
  ]);
});

test("empty search with no repository field is a no-match", () => {
  const state = searchEmptyState({ query: "x", manager: "apk", count: 0, results: [] });
  assert.strictEqual(state.kind, "no-match");
});

test("index-unavailable status maps to its own message", () => {
  const state = searchEmptyState({
    query: "luci",
    manager: "apk",
    count: 0,
    results: [],
    repository: {
      status: "index-unavailable",
      available: false,
      reason: "apk could not open its cache indexes on the router.",
      detail: ["WARNING: opening from cache /var/cache/apk: No such file or directory"],
    },
  });
  assert.strictEqual(state.kind, "index-unavailable");
  assert.match(state.title, /metadata is unavailable/);
  assert.strictEqual(state.reason, "apk could not open its cache indexes on the router.");
});

test("manager-unavailable status maps to its own message", () => {
  const state = searchEmptyState({
    query: "luci",
    manager: "unknown",
    count: 0,
    results: [],
    repository: {
      status: "manager-unavailable",
      available: false,
      reason: "No supported package manager (apk or opkg) was found on the router.",
    },
  });
  assert.strictEqual(state.kind, "manager-unavailable");
  assert.match(state.title, /package manager is unavailable/);
});

test("repository-unavailable status maps to its own message", () => {
  const state = searchEmptyState({
    query: "luci",
    manager: "opkg",
    count: 0,
    results: [],
    repository: {
      status: "repository-unavailable",
      available: false,
      reason: "The repository index has not been downloaded on the router.",
    },
  });
  assert.strictEqual(state.kind, "repository-unavailable");
  assert.match(state.title, /repository is unavailable/);
  assert.strictEqual(state.reason, "The repository index has not been downloaded on the router.");
});

// -- storage: read-only firmware /rom -------------------------------------- //

test("squashfs /rom is a read-only firmware mount", () => {
  assert.strictEqual(isReadonlyFirmwareMount(mount()), true);
  assert.strictEqual(
    isReadonlyFirmwareMount(mount({ filesystem: "erofs" })),
    true,
  );
  assert.strictEqual(
    isReadonlyFirmwareMount(mount({ filesystem: "overlay" })),
    false,
  );
  assert.strictEqual(
    isReadonlyFirmwareMount(mount({ filesystem: "jffs2" })),
    false,
  );
  assert.strictEqual(isReadonlyFirmwareMount(mount({ filesystem: "" })), false);
});

test("read-only firmware mounts are always a neutral tone", () => {
  assert.strictEqual(mountUsageTone(100, mount()), "neutral");
  assert.strictEqual(mountUsageTone(50, mount({ filesystem: "erofs" })), "neutral");
});

test("writable mounts use normal thresholds", () => {
  const writable = mount({ filesystem: "overlay", use_percent: 36 });
  assert.strictEqual(mountUsageTone(36, writable), "good");
  assert.strictEqual(mountUsageTone(85, writable), "warn");
  assert.strictEqual(mountUsageTone(95, writable), "danger");
  assert.strictEqual(mountUsageTone(null, writable), "neutral");
});

test("df header artifact is a bogus mount and is filtered out", () => {
  const bogus = mount({
    device: "Filesystem",
    mountpoint: "Mounted on",
    total_bytes: 0,
    used_bytes: 0,
    available_bytes: 0,
    use_percent: null,
  });
  assert.strictEqual(isBogusMount(bogus), true);
  assert.strictEqual(isBogusMount(mount()), false);

  const mounts = usableMounts([bogus, mount(), mount({ mountpoint: "/overlay" })]);
  assert.strictEqual(mounts.length, 2);
  assert.ok(!mounts.some((entry) => isBogusMount(entry)));
});

test("normal writable mounts are unchanged", () => {
  const overlay = mount({ device: "overlayfs:/overlay", mountpoint: "/", filesystem: "overlay", use_percent: 36, overlay: true, rootfs: true });
  const tmpfs = mount({ device: "tmpfs", mountpoint: "/tmp", filesystem: "tmpfs", use_percent: 21 });
  const mounts = usableMounts([overlay, tmpfs]);
  assert.deepStrictEqual(mounts, [overlay, tmpfs]);
});
