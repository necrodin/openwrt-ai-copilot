// Internet speed-test regression tests.
//
// Exercise the real `lib/speed-test.ts` module (loaded via jiti, never a
// reimplementation): result formatting, the "Never"/timestamp label, stage
// labels, and the API client against a stubbed `fetch` (success, failure,
// and latest-result reads).
import test from "node:test";
import assert from "node:assert";

import { loadSpeedTestModule } from "./helpers.mjs";

const {
  speedStageLabel,
  formatSpeed,
  formatLatency,
  formatSpeedTestTimestamp,
  runSpeedTest,
  latestSpeedTest,
} = loadSpeedTestModule();

const RESULT = {
  download_mbps: 245.4,
  upload_mbps: 38.2,
  ping_ms: 12.4,
  jitter_ms: 2.8,
  timestamp: "2026-08-14T00:00:00Z",
  duration_ms: 12345,
  limitations: [],
  complete: true,
};

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function stubFetch(handler) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (input, init = {}) => {
    const method = init.method ?? "GET";
    const url = typeof input === "string" ? input : input.url;
    calls.push({ method, url, body: init.body });
    return handler(method, url);
  };
  return { calls, restore: () => (globalThis.fetch = original) };
}

test("formatSpeed renders a value or an em dash when not measured", () => {
  assert.strictEqual(formatSpeed(245.4), "245.4");
  assert.strictEqual(formatSpeed(0), "0.0");
  assert.strictEqual(formatSpeed(null), "—");
});

test("formatLatency renders ms or an em dash when not measured", () => {
  assert.strictEqual(formatLatency(12.4), "12.4");
  assert.strictEqual(formatLatency(null), "—");
});

test("speedStageLabel maps every stage to a progress label", () => {
  assert.strictEqual(speedStageLabel("testing"), "Testing…");
  assert.strictEqual(speedStageLabel("latency"), "Latency…");
  assert.strictEqual(speedStageLabel("downloading"), "Download…");
  assert.strictEqual(speedStageLabel("uploading"), "Upload…");
});

test("formatSpeedTestTimestamp shows Never before any test", () => {
  assert.strictEqual(formatSpeedTestTimestamp(null), "Never");
  assert.strictEqual(formatSpeedTestTimestamp(undefined), "Never");
  assert.strictEqual(formatSpeedTestTimestamp("not-a-date"), "Never");
});

test("formatSpeedTestTimestamp renders a real timestamp", () => {
  const label = formatSpeedTestTimestamp(RESULT.timestamp);
  assert.notStrictEqual(label, "Never");
  assert.ok(label.includes("2026"));
});

test("runSpeedTest POSTs to /network/speed-test and resolves the result", async () => {
  const { calls, restore } = stubFetch(() => jsonResponse(200, RESULT));
  try {
    const result = await runSpeedTest();
    assert.strictEqual(result.download_mbps, 245.4);
    assert.strictEqual(result.ping_ms, 12.4);
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/network/speed-test"));
  } finally {
    restore();
  }
});

test("runSpeedTest surfaces a backend 409 (already running) as an error", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(409, { detail: "A speed test is already running." }),
  );
  try {
    await assert.rejects(() => runSpeedTest(), /already running/);
  } finally {
    restore();
  }
});

test("runSpeedTest surfaces a backend 502 (measurement failure) as an error", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(502, { detail: "Could not reach latency target 1.1.1.1:443." }),
  );
  try {
    await assert.rejects(() => runSpeedTest(), /latency target/);
  } finally {
    restore();
  }
});

test("runSpeedTest surfaces a backend 429 (cooldown) as an error", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(429, { detail: "A speed test ran too recently; try again shortly." }),
  );
  try {
    await assert.rejects(() => runSpeedTest(), /too recently/);
  } finally {
    restore();
  }
});

test("runSpeedTest degrades gracefully on a partial (incomplete) result", async () => {
  const partial = {
    ...RESULT,
    upload_mbps: null,
    complete: false,
    limitations: ["Upload could not be measured: timed out"],
  };
  const { restore } = stubFetch(() => jsonResponse(200, partial));
  try {
    const result = await runSpeedTest();
    assert.strictEqual(result.upload_mbps, null);
    assert.strictEqual(result.complete, false);
    assert.ok(result.limitations.length === 1);
    // The UI renders the missing value as an em dash.
    assert.strictEqual(formatSpeed(result.upload_mbps), "—");
    assert.strictEqual(formatSpeed(result.download_mbps), "245.4");
  } finally {
    restore();
  }
});

test("latestSpeedTest returns the stored result", async () => {
  const { calls, restore } = stubFetch(() => jsonResponse(200, { result: RESULT }));
  try {
    const response = await latestSpeedTest();
    assert.strictEqual(response.result.timestamp, RESULT.timestamp);
    assert.strictEqual(calls[0].method, "GET");
    assert.ok(calls[0].url.endsWith("/api/v1/network/speed-test"));
  } finally {
    restore();
  }
});

test("latestSpeedTest returns null before the first run", async () => {
  const { restore } = stubFetch(() => jsonResponse(200, { result: null }));
  try {
    const response = await latestSpeedTest();
    assert.strictEqual(response.result, null);
  } finally {
    restore();
  }
});

test("latestSpeedTest rejects with a clear message on failure", async () => {
  const { restore } = stubFetch(() => jsonResponse(500, { detail: "boom" }));
  try {
    await assert.rejects(() => latestSpeedTest(), /boom/);
  } finally {
    restore();
  }
});
