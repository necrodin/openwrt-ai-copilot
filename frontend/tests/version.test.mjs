// Version metadata regression tests.
//
// An unstamped build must never fabricate a version number: with no
// NEXT_PUBLIC_* stamp the About page renders "N/A" rather than a placeholder
// like "0.0.0". Git commit / build date are null until injected at build time,
// and the dev environment stays "development".
import test from "node:test";
import assert from "node:assert";

delete process.env.NEXT_PUBLIC_APP_VERSION;
delete process.env.NEXT_PUBLIC_FRONTEND_VERSION;
delete process.env.NEXT_PUBLIC_GIT_COMMIT;
delete process.env.NEXT_PUBLIC_BUILD_DATE;
delete process.env.NEXT_PUBLIC_ENVIRONMENT;

const { getFrontendVersionInfo } = (await import("./helpers.mjs")).loadVersionModule();

test("unstamped build reports null versions, never 0.0.0", () => {
  const info = getFrontendVersionInfo();
  assert.strictEqual(info.version, null);
  assert.strictEqual(info.frontendVersion, null);
});

test("unstamped build reports null git commit and build date", () => {
  const info = getFrontendVersionInfo();
  assert.strictEqual(info.gitCommit, null);
  assert.strictEqual(info.buildDate, null);
});

test("dev environment stays development", () => {
  const info = getFrontendVersionInfo();
  assert.strictEqual(info.environment, "development");
});
