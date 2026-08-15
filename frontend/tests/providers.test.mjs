// AI Provider configuration tests.
//
// Exercise the real `lib/providers.ts` module (loaded via jiti, never a
// reimplementation): request building, credential masking/preservation, the
// admin-only mutation gate, default sorting, and error mapping. API calls are
// exercised against a stubbed `fetch` that records the method/path/body so we
// can assert exactly what would be sent to the backend.
import test from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";

import { loadProvidersModule } from "./helpers.mjs";

const {
  FORM_SECTIONS,
  emptyFormValues,
  editFormValues,
  defaultBaseUrl,
  hasConfiguredCredential,
  canMutateProviders,
  buildCreatePayload,
  buildUpdatePayload,
  buildProbePayload,
  sortProviders,
  selectableProviders,
  chatSelection,
  providerTestCategoryLabel,
  apiErrorMessage,
  listProviders,
  createProvider,
  updateProvider,
  deleteProvider,
  enableProvider,
  disableProvider,
  setDefaultProvider,
  removeProviderCredential,
  testProviderConnection,
  testProviderConfig,
  discoverProviderModels,
} = loadProvidersModule();

const TYPES = [
  { type: "lmstudio", default_base_url: "http://localhost:1234/v1" },
  { type: "openai", default_base_url: "https://api.openai.com/v1" },
];

function provider(overrides = {}) {
  return {
    type: "openai",
    name: "OpenAI",
    base_url: "https://api.openai.com/v1",
    enabled: true,
    is_default: false,
    has_credential: false,
    model: "gpt-4o-mini",
    static_capabilities: ["chat", "embedding"],
    ...overrides,
  };
}

function jsonResponse(status, body) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

/** Stub global fetch; `handler` receives (method, url, body) and returns a Response. */
function stubFetch(handler) {
  const calls = [];
  const original = globalThis.fetch;
  globalThis.fetch = async (input, init = {}) => {
    const method = init.method ?? "GET";
    const url = typeof input === "string" ? input : input.url;
    const body = init.body ? JSON.parse(init.body) : undefined;
    calls.push({ method, url, body });
    return handler(method, url, body);
  };
  return { calls, restore: () => (globalThis.fetch = original) };
}

test("emptyFormValues returns a blank create form with a safe default", () => {
  const form = emptyFormValues();
  assert.deepStrictEqual(form, {
    type: "",
    name: "",
    baseUrl: "",
    apiKey: "",
    model: "",
    enabled: true,
  });
});

test("emptyFormValues returns a fresh, independent draft every call", () => {
  const first = emptyFormValues();
  const second = emptyFormValues();
  assert.notStrictEqual(first, second);
  first.type = "openai";
  first.model = "leaked-model";
  first.apiKey = "sk-should-not-leak";
  // The next draft must never be polluted by a previous draft.
  assert.deepStrictEqual(emptyFormValues(), {
    type: "",
    name: "",
    baseUrl: "",
    apiKey: "",
    model: "",
    enabled: true,
  });
});

test("form section order is Provider -> API Key -> Model (discovery/test depend on credential)", () => {
  const order = [...FORM_SECTIONS];
  assert.deepStrictEqual(order, [
    "type",
    "name",
    "baseUrl",
    "apiKey",
    "discoverModels",
    "model",
    "testConnection",
    "enabled",
    "save",
  ]);
  // The API key must come strictly before the model.
  assert.ok(order.indexOf("apiKey") < order.indexOf("model"));
  // Discovery (which needs the credential) sits between API key and model.
  assert.ok(order.indexOf("apiKey") < order.indexOf("discoverModels"));
  assert.ok(order.indexOf("discoverModels") < order.indexOf("model"));
});

test("a new provider can never overwrite an existing one (create uses POST /providers and a 409 surfaces)", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(409, { detail: "Provider 'openai' already exists." }),
  );
  try {
    await assert.rejects(
      () => createProvider({ type: "openai", name: "OpenAI" }),
      /already exists/,
    );
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/providers"));
    // Create never PATCHes an existing provider type.
    assert.ok(!calls[0].url.includes("/providers/openai"));
  } finally {
    restore();
  }
});

test("delete targets exactly the selected provider type", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, { deleted: true, type: "deepseek" }),
  );
  try {
    const result = await deleteProvider("deepseek");
    assert.strictEqual(result.deleted, true);
    assert.strictEqual(calls[0].method, "DELETE");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/deepseek"));
    assert.ok(!calls[0].url.includes("openai"));
  } finally {
    restore();
  }
});

test("delete surfaces the real backend error on failure (never silently passes)", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(404, { detail: "Provider 'deepseek' is not configured" }),
  );
  try {
    await assert.rejects(() => deleteProvider("deepseek"), /not configured/);
  } finally {
    restore();
  }
});

test("provider module never reads or writes browser storage (API key can never persist client-side)", () => {
  const source = readFileSync(new URL("../lib/providers.ts", import.meta.url), "utf8");
  assert.ok(!source.includes("localStorage"));
  assert.ok(!source.includes("sessionStorage"));
});

test("editFormValues preloads provider fields but never the credential", () => {
  const form = editFormValues(provider({ has_credential: true, model: "gpt-4o" }));
  assert.strictEqual(form.type, "openai");
  assert.strictEqual(form.name, "OpenAI");
  assert.strictEqual(form.baseUrl, "https://api.openai.com/v1");
  assert.strictEqual(form.model, "gpt-4o");
  assert.strictEqual(form.enabled, true);
  // The stored credential is only a boolean flag; the edit form must not
  // reveal any reference to the underlying key value.
  assert.strictEqual(form.apiKey, "");
});

test("defaultBaseUrl resolves the canonical URL for a type", () => {
  assert.strictEqual(defaultBaseUrl(TYPES, "openai"), "https://api.openai.com/v1");
  assert.strictEqual(defaultBaseUrl(TYPES, "lmstudio"), "http://localhost:1234/v1");
  assert.strictEqual(defaultBaseUrl(TYPES, "unknown"), "");
});

test("hasConfiguredCredential reflects the backend boolean flag only", () => {
  assert.strictEqual(hasConfiguredCredential(provider({ has_credential: true })), true);
  assert.strictEqual(hasConfiguredCredential(provider({ has_credential: false })), false);
});

test("only admin operators may mutate providers", () => {
  assert.strictEqual(canMutateProviders("admin"), true);
  assert.strictEqual(canMutateProviders("readonly"), false);
  assert.strictEqual(canMutateProviders(null), false);
  assert.strictEqual(canMutateProviders(undefined), false);
});

test("buildCreatePayload sends the write-only credential when provided", () => {
  const payload = buildCreatePayload({
    type: "openai",
    name: "  My OpenAI  ",
    baseUrl: " https://api.openai.com/v1 ",
    apiKey: " sk-live-123 ",
    model: "gpt-4o",
    enabled: false,
  });
  assert.deepStrictEqual(payload, {
    type: "openai",
    name: "My OpenAI",
    enabled: false,
    base_url: "https://api.openai.com/v1",
    model: "gpt-4o",
    credential: "sk-live-123",
  });
});

test("buildCreatePayload omits the credential when the field is empty", () => {
  const payload = buildCreatePayload(emptyFormValues());
  assert.ok(!("credential" in payload));
  assert.ok(!("api_key_env" in payload));
  assert.strictEqual(payload.base_url, null);
});

test("buildUpdatePayload preserves the existing credential when left empty", () => {
  const form = editFormValues(provider({ has_credential: true }));
  const payload = buildUpdatePayload(form);
  // No credential key at all -> backend keeps the configured credential.
  assert.ok(!("credential" in payload));
  assert.strictEqual(payload.name, "OpenAI");
  assert.strictEqual(payload.model, "gpt-4o-mini");
  assert.strictEqual(payload.base_url, "https://api.openai.com/v1");
});

test("buildUpdatePayload replaces the credential only when a new key is entered", () => {
  const form = { ...editFormValues(provider({ has_credential: true })), apiKey: "sk-new-1" };
  const payload = buildUpdatePayload(form);
  assert.strictEqual(payload.credential, "sk-new-1");
});

test("buildUpdatePayload can clear the base URL but empty API key never clears credential", () => {
  const form = { ...editFormValues(provider()), baseUrl: "  " };
  const payload = buildUpdatePayload(form);
  assert.strictEqual(payload.base_url, null);
  assert.ok(!("credential" in payload));
});

test("sortProviders lists the default first, then by type", () => {
  const providers = [
    provider({ type: "nim", name: "NIM" }),
    provider({ type: "openai", name: "OpenAI", is_default: true }),
    provider({ type: "ollama", name: "Ollama" }),
  ];
  const sorted = sortProviders(providers);
  assert.deepStrictEqual(
    sorted.map((entry) => entry.type),
    ["openai", "nim", "ollama"],
  );
});

test("selectableProviders keeps only enabled providers (default first)", () => {
  const providers = [
    provider({ type: "nim", name: "NIM", enabled: false }),
    provider({ type: "openai", name: "OpenAI", enabled: true, is_default: true }),
    provider({ type: "ollama", name: "Ollama", enabled: true }),
  ];
  const selectable = selectableProviders(providers);
  assert.deepStrictEqual(
    selectable.map((entry) => entry.type),
    ["openai", "ollama"],
  );
});

test("selectableProviders returns an empty list when nothing is enabled", () => {
  assert.deepStrictEqual(
    selectableProviders([provider({ enabled: false }), provider({ type: "ollama", enabled: false })]),
    [],
  );
});

test("chatSelection maps a selected provider to the request provider and its configured model", () => {
  const providers = selectableProviders([
    provider({ type: "openai", model: "gpt-4o" }),
    provider({ type: "ollama", model: "llama3" }),
  ]);
  assert.deepStrictEqual(chatSelection(providers, "ollama"), {
    provider: "ollama",
    model: "llama3",
  });
  // A provider without a configured model still routes to the provider.
  assert.deepStrictEqual(
    chatSelection(providers, "openai"),
    { provider: "openai", model: "gpt-4o" },
  );
});

test("chatSelection applies a manual model override only when non-empty", () => {
  const providers = selectableProviders([
    provider({ type: "openai", model: "gpt-4o" }),
    provider({ type: "ollama", model: "llama3" }),
  ]);
  assert.deepStrictEqual(chatSelection(providers, "openai", "gpt-4o-mini"), {
    provider: "openai",
    model: "gpt-4o-mini",
  });
  // An empty/whitespace override falls back to the provider's configured model.
  assert.deepStrictEqual(chatSelection(providers, "ollama", ""), {
    provider: "ollama",
    model: "llama3",
  });
  assert.deepStrictEqual(chatSelection(providers, "ollama", "  "), {
    provider: "ollama",
    model: "llama3",
  });
  // An override never re-anchors an unknown/disabled provider.
  assert.deepStrictEqual(chatSelection(providers, "missing", "custom-1"), {
    provider: null,
    model: null,
  });
});

test("chatSelection falls back to the backend default for unknown or disabled providers", () => {
  const providers = selectableProviders([provider({ type: "openai", model: "gpt-4o" })]);
  assert.deepStrictEqual(chatSelection(providers, null), { provider: null, model: null });
  assert.deepStrictEqual(chatSelection(providers, "missing"), { provider: null, model: null });
  // A provider enabled at load time but now disabled must not pin the request.
  assert.deepStrictEqual(
    chatSelection([...providers, provider({ type: "nim", enabled: false })], "nim"),
    { provider: null, model: null },
  );
});

test("chatSelection exposes only provider/model identifiers, never credentials", () => {
  const providers = selectableProviders([provider({ has_credential: true })]);
  const selection = chatSelection(providers, "openai");
  // The selection carries no key value or env-var reference — only the two
  // identifiers the chat API accepts.
  assert.deepStrictEqual(Object.keys(selection).sort(), ["model", "provider"]);
  assert.ok(!JSON.stringify(selection).includes("api_key"));
  assert.ok(!JSON.stringify(selection).includes("sk-"));
});

test("chatSelection is side-effect free (conversation and list stay intact)", () => {
  const providers = selectableProviders([provider({ type: "openai", model: "gpt-4o" })]);
  const snapshot = JSON.stringify(providers);
  chatSelection(providers, "openai");
  assert.strictEqual(JSON.stringify(providers), snapshot);
});

test("multiple providers are selectable in the Copilot selector", () => {
  const providers = selectableProviders([
    provider({ type: "openrouter", name: "OpenRouter" }),
    provider({ type: "ollama", name: "Ollama" }),
    provider({ type: "openai", name: "OpenAI", is_default: true }),
  ]);
  assert.deepStrictEqual(
    providers.map((entry) => entry.type),
    ["openai", "ollama", "openrouter"],
  );
  // Switching the selection never changes the configured global default.
  assert.deepStrictEqual(chatSelection(providers, "ollama"), {
    provider: "ollama",
    model: "gpt-4o-mini",
  });
  assert.strictEqual(providers.find((entry) => entry.is_default)?.type, "openai");
});

test("buildProbePayload sends the write-only credential for the draft probe", () => {
  const payload = buildProbePayload({
    type: "compat",
    name: "  My AI  ",
    baseUrl: " https://example.com/v1 ",
    apiKey: " sk-live-456 ",
    model: "some-model",
    enabled: true,
  });
  assert.deepStrictEqual(payload, {
    type: "compat",
    name: "My AI",
    base_url: "https://example.com/v1",
    model: "some-model",
    credential: "sk-live-456",
  });
  assert.ok(!("api_key_env" in payload));
});

test("buildProbePayload omits the credential when none was typed", () => {
  const payload = buildProbePayload({ ...emptyFormValues(), type: "openai" });
  assert.ok(!("credential" in payload));
});

test("testProviderConfig POSTs the draft to /providers/test and resolves the categorized result", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, {
      ok: true,
      category: "ok",
      message: "Connection OK",
      model: "gpt-4o",
      latency_ms: 120,
    }),
  );
  try {
    const result = await testProviderConfig({ type: "openai", model: "gpt-4o" });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.category, "ok");
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/test"));
    assert.deepStrictEqual(calls[0].body, { type: "openai", model: "gpt-4o" });
  } finally {
    restore();
  }
});

test("testProviderConfig sends the unsaved credential for the probe and nothing echoes back", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, { ok: true, category: "ok", message: "OK" }),
  );
  try {
    const result = await testProviderConfig({ type: "openai", credential: "sk-draft-9", model: "gpt-4o" });
    assert.strictEqual(result.ok, true);
    assert.deepStrictEqual(calls[0].body, {
      type: "openai",
      credential: "sk-draft-9",
      model: "gpt-4o",
    });
    assert.ok(!JSON.stringify(calls[0].body).includes("api_key_env"));
  } finally {
    restore();
  }
});

test("testProviderConfig surfaces a categorized failure", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(200, { ok: false, category: "authentication_failed", message: "bad key" }),
  );
  try {
    const result = await testProviderConfig({ type: "openai", model: "gpt-4o" });
    assert.strictEqual(result.ok, false);
    assert.strictEqual(result.category, "authentication_failed");
  } finally {
    restore();
  }
});

test("discoverProviderModels POSTs to /providers/discover-models and lists models", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, {
      ok: true,
      models: [{ id: "gpt-4o", capabilities: ["chat"], context_window: null }],
    }),
  );
  try {
    const result = await discoverProviderModels({
      type: "openai",
      base_url: "https://x/v1",
      credential: "sk-discover-1",
    });
    assert.strictEqual(result.ok, true);
    assert.strictEqual(result.models[0].id, "gpt-4o");
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/discover-models"));
    // Discovery uses the draft credential exactly as typed.
    assert.strictEqual(calls[0].body.credential, "sk-discover-1");
    assert.ok(!JSON.stringify(calls[0].body).includes("api_key_env"));
  } finally {
    restore();
  }
});

test("discoverProviderModels reports a categorized failure so manual entry remains", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(200, { ok: false, category: "endpoint_unreachable", message: "nope" }),
  );
  try {
    const result = await discoverProviderModels({ type: "openai" });
    assert.strictEqual(result.ok, false);
    assert.strictEqual(result.category, "endpoint_unreachable");
  } finally {
    restore();
  }
});

test("providerTestCategoryLabel renders a stable label for every category", () => {
  assert.strictEqual(providerTestCategoryLabel("ok"), "Connection OK");
  assert.strictEqual(providerTestCategoryLabel("endpoint_unreachable"), "Endpoint unreachable");
  assert.strictEqual(providerTestCategoryLabel("authentication_failed"), "Authentication failed");
  assert.strictEqual(providerTestCategoryLabel("model_not_found"), "Model not found");
  assert.strictEqual(providerTestCategoryLabel("rate_limited"), "Rate limited");
  assert.strictEqual(providerTestCategoryLabel("provider_rejected"), "Provider rejected the request");
  assert.strictEqual(providerTestCategoryLabel("timeout"), "Timed out");
  assert.strictEqual(providerTestCategoryLabel("invalid_configuration"), "Invalid configuration");
});

test("testProviderConnection POSTs to /providers/{type}/test and returns the model-test result", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, { ok: false, category: "model_not_found", message: "missing" }),
  );
  try {
    const result = await testProviderConnection("openai");
    assert.strictEqual(result.category, "model_not_found");
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/openai/test"));
  } finally {
    restore();
  }
});

test("apiErrorMessage surfaces the backend detail", async () => {
  const res = jsonResponse(400, { detail: "Unsupported provider type 'x'" });
  assert.strictEqual(await apiErrorMessage(res), "Unsupported provider type 'x'");
});

test("apiErrorMessage falls back to a status message for non-JSON bodies", async () => {
  const res = new Response("boom", { status: 502 });
  assert.strictEqual(await apiErrorMessage(res), "Request failed with status 502");
});

test("listProviders resolves providers and rejects with a clear error on failure", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, {
      service: "test",
      default_provider: "openai",
      providers: [provider()],
    }),
  );
  try {
    const list = await listProviders();
    assert.strictEqual(calls[0].method, "GET");
    assert.ok(calls[0].url.endsWith("/api/v1/providers"));
    assert.strictEqual(list.default_provider, "openai");
    assert.strictEqual(list.providers[0].type, "openai");
  } finally {
    restore();
  }

  const { restore: restoreFail } = stubFetch(() => jsonResponse(500, { detail: "nope" }));
  try {
    await assert.rejects(() => listProviders(), /nope/);
  } finally {
    restoreFail();
  }
});

test("createProvider POSTs the create payload to /providers", async () => {
  const { calls, restore } = stubFetch(() => jsonResponse(201, provider({ name: "OpenAI" })));
  try {
    const result = await createProvider({ type: "openai", name: "OpenAI" });
    assert.strictEqual(result.name, "OpenAI");
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/providers"));
    assert.deepStrictEqual(calls[0].body, { type: "openai", name: "OpenAI" });
  } finally {
    restore();
  }
});

test("updateProvider PATCHes /providers/{type} without touching the credential", async () => {
  const { calls, restore } = stubFetch(() => jsonResponse(200, provider()));
  try {
    await updateProvider("openai", { name: "OpenAI", model: "gpt-4o" });
    assert.strictEqual(calls[0].method, "PATCH");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/openai"));
    assert.deepStrictEqual(calls[0].body, { name: "OpenAI", model: "gpt-4o" });
  } finally {
    restore();
  }
});

test("removeProviderCredential DELETEs /providers/{type}/credential for explicit removal", async () => {
  const { calls, restore } = stubFetch(() =>
    jsonResponse(200, { removed: true, type: "openai" }),
  );
  try {
    const result = await removeProviderCredential("openai");
    assert.strictEqual(result.removed, true);
    assert.strictEqual(calls[0].method, "DELETE");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/openai/credential"));
    assert.strictEqual(calls[0].body, undefined);
  } finally {
    restore();
  }
});

test("deleteProvider DELETEs /providers/{type} and returns the acknowledgement", async () => {
  const { calls, restore } = stubFetch(() => jsonResponse(200, { deleted: true, type: "openai" }));
  try {
    const result = await deleteProvider("openai");
    assert.strictEqual(result.deleted, true);
    assert.strictEqual(calls[0].method, "DELETE");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/openai"));
    assert.strictEqual(calls[0].body, undefined);
  } finally {
    restore();
  }
});

test("enableProvider and disableProvider POST to the dedicated actions", async () => {
  const { calls: enableCalls, restore: restoreEnable } = stubFetch(() =>
    jsonResponse(200, provider({ enabled: true })),
  );
  try {
    await enableProvider("openai");
    assert.strictEqual(enableCalls[0].method, "POST");
    assert.ok(enableCalls[0].url.endsWith("/api/v1/providers/openai/enable"));
  } finally {
    restoreEnable();
  }

  const { calls: disableCalls, restore: restoreDisable } = stubFetch(() =>
    jsonResponse(200, provider({ enabled: false })),
  );
  try {
    await disableProvider("openai");
    assert.strictEqual(disableCalls[0].method, "POST");
    assert.ok(disableCalls[0].url.endsWith("/api/v1/providers/openai/disable"));
  } finally {
    restoreDisable();
  }
});

test("setDefaultProvider POSTs the type to /providers/default", async () => {
  const { calls, restore } = stubFetch(() => jsonResponse(200, { default_provider: "openai" }));
  try {
    const result = await setDefaultProvider("openai");
    assert.strictEqual(result.default_provider, "openai");
    assert.strictEqual(calls[0].method, "POST");
    assert.ok(calls[0].url.endsWith("/api/v1/providers/default"));
    assert.deepStrictEqual(calls[0].body, { type: "openai" });
  } finally {
    restore();
  }
});

test("a read-only operator's mutation attempt surfaces the backend 403 detail", async () => {
  const { restore } = stubFetch(() =>
    jsonResponse(403, { detail: "Insufficient permissions" }),
  );
  try {
    await assert.rejects(() => enableProvider("openai"), /Insufficient permissions/);
  } finally {
    restore();
  }
});
