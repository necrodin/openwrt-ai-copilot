// WAN IP vs Public IP label regression tests.
import test from "node:test";
import assert from "node:assert";

import { loadDashboardUtilsModule } from "./helpers.mjs";

const { wanAddressLabel } = loadDashboardUtilsModule();

test("private WAN address is never labelled Public IP", () => {
  assert.strictEqual(wanAddressLabel(false), "WAN IP");
  assert.strictEqual(wanAddressLabel(null), "WAN IP");
  assert.strictEqual(wanAddressLabel(undefined), "WAN IP");
});

test("genuinely public address is labelled Public IP", () => {
  assert.strictEqual(wanAddressLabel(true), "Public IP");
});