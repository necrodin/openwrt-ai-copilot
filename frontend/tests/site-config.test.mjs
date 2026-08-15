// Site config regression tests.
//
// The Support Development page must expose exactly the two maintainer-owned
// donation targets — GitHub Sponsors and an Amazon Gift Card — with real links,
// and must never fabricate donation addresses. These values are static config,
// not user-configurable.
import test from "node:test";
import assert from "node:assert";

delete process.env.NEXT_PUBLIC_DONATE_GITHUB;
delete process.env.NEXT_PUBLIC_DONATE_AMAZON;

const { SITE_CONFIG } = (await import("./helpers.mjs")).loadSiteConfigModule();

test("support page has exactly two donation targets", () => {
  assert.strictEqual(SITE_CONFIG.donations.length, 2);
});

test("github sponsors target links to the real maintainer profile", () => {
  const github = SITE_CONFIG.donations.find((target) => target.id === "github-sponsors");
  assert.ok(github, "github-sponsors target is present");
  assert.strictEqual(github.url, "https://github.com/necrodin");
});

test("amazon gift card target links to the maintainer email", () => {
  const amazon = SITE_CONFIG.donations.find((target) => target.id === "amazon-gift-card");
  assert.ok(amazon, "amazon-gift-card target is present");
  assert.strictEqual(amazon.url, "mailto:necrodin@gmail.com");
});

test("removed donation methods are gone", () => {
  const labels = SITE_CONFIG.donations.map((target) => target.label);
  for (const removed of [
    "Buy Me a Coffee",
    "Ko-fi",
    "PayPal",
    "Bitcoin (BTC)",
    "Ethereum (ETH)",
    "Lightning Network",
  ]) {
    assert.ok(!labels.includes(removed), `${removed} must not be a donation target`);
  }
});
