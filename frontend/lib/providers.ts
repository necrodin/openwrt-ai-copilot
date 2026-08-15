/**
 * Provider configuration API client and presentation logic.
 *
 * Mirrors the backend surface under /api/v1/providers. Reads work for any
 * authenticated role; every mutation (create / update / delete / enable /
 * disable / set-default / test-connection / remove-credential) requires the
 * existing admin/write scope and is enforced by the backend — the UI only
 * hides the controls for read-only operators.
 *
 * Credentials: the operator enters the ACTUAL API key in the form. The key is
 * write-only — it is encrypted into the backend's server-side credential store
 * and is never returned by, stored by, or sent back from the backend. The form
 * never populates the key input (the stored credential is only a boolean
 * ``has_credential``), leaving the field empty on edit preserves the existing
 * credential, and entering a new key replaces it (all enforced server-side).
 */

import { API_BASE_URL } from "@/lib/api";
import { authHeaders, type AuthRole } from "@/lib/auth";

export type ProviderTypeInfo = {
  type: string;
  /** Human-facing name from the backend (never hardcoded in the UI). */
  label: string;
  default_base_url: string;
  /** True when the endpoint must be supplied (e.g. custom OpenAI-compatible). */
  requires_base_url: boolean;
};

export type ProviderSummary = {
  /** Config key / identity used in the API (equal to the provider type). */
  type: string;
  /** Human-facing name (falls back to the type when unset). */
  name: string;
  base_url: string;
  enabled: boolean;
  is_default: boolean;
  /** True when an API-key credential is configured (value never exposed). */
  has_credential: boolean;
  model: string;
  static_capabilities: string[];
};

export type ProviderListResponse = {
  service: string;
  default_provider: string | null;
  providers: ProviderSummary[];
};

export type ProviderTypesResponse = {
  service: string;
  types: ProviderTypeInfo[];
};

/** Draft provider configuration used to test/discover before saving. The API
 * key (``credential``) is write-only: sent once for the probe and never
 * returned or stored. */
export type ProviderProbePayload = {
  type: string;
  name?: string;
  base_url?: string | null;
  credential?: string;
  model?: string;
  timeout_seconds?: number;
  verify_tls?: boolean;
};

/** Stable failure categories mirrored from the backend. */
export type ProviderTestCategory =
  | "ok"
  | "endpoint_unreachable"
  | "authentication_failed"
  | "model_not_found"
  | "rate_limited"
  | "provider_rejected"
  | "timeout"
  | "invalid_configuration";

export type ProviderTestResult = {
  ok: boolean;
  category: ProviderTestCategory;
  message: string;
  model?: string;
  reply?: string;
  latency_ms?: number;
};

export type ProviderModel = {
  id: string;
  capabilities: string[];
  context_window: number | null;
};

export type ModelDiscoveryResult = {
  ok: boolean;
  category?: ProviderTestCategory;
  message?: string;
  models?: ProviderModel[];
};

export type ProviderFormValues = {
  type: string;
  name: string;
  baseUrl: string;
  /** The ACTUAL API key, write-only. Empty when editing (never populated). */
  apiKey: string;
  model: string;
  enabled: boolean;
};

/** Stable, empty form used to start an "add provider" flow. */
export function emptyFormValues(): ProviderFormValues {
  return { type: "", name: "", baseUrl: "", apiKey: "", model: "", enabled: true };
}

/** Prefilled form for editing an existing provider. The API-key field stays
 * empty so an unchanged value preserves the existing credential; the stored
 * credential is only a boolean flag and is never revealed to the browser. */
export function editFormValues(provider: ProviderSummary): ProviderFormValues {
  return {
    type: provider.type,
    name: provider.name,
    baseUrl: provider.base_url,
    apiKey: "",
    model: provider.model,
    enabled: provider.enabled,
  };
}

/** The canonical default base URL for a provider type, or "" when unknown. */
export function defaultBaseUrl(types: ProviderTypeInfo[], type: string): string {
  const found = types.find((entry) => entry.type === type);
  return found?.default_base_url ?? "";
}

/** Whether a provider already has a configured API-key credential. */
export function hasConfiguredCredential(provider: ProviderSummary): boolean {
  return provider.has_credential === true;
}

/** Admin-only gate for provider mutations. Read-only operators can view. */
export function canMutateProviders(role: AuthRole | null | undefined): boolean {
  return role === "admin";
}

/** Build the POST /providers body from form values. The API key (``credential``)
 * is included only when the operator provided one; it is write-only and never
 * echoed back. */
export function buildCreatePayload(form: ProviderFormValues): Record<string, unknown> {
  const credential = form.apiKey.trim();
  return {
    type: form.type,
    name: form.name.trim(),
    enabled: form.enabled,
    base_url: form.baseUrl.trim() || null,
    model: form.model.trim(),
    ...(credential ? { credential } : {}),
  };
}

/** Build the PATCH /providers/{type} body from form values. An omitted
 * ``credential`` (empty field) preserves the existing credential — enforced
 * server-side. A non-empty ``credential`` replaces it. */
export function buildUpdatePayload(
  form: ProviderFormValues,
): Record<string, unknown> {
  const credential = form.apiKey.trim();
  return {
    name: form.name.trim(),
    enabled: form.enabled,
    model: form.model.trim(),
    base_url: form.baseUrl.trim() || null,
    ...(credential ? { credential } : {}),
  };
}

/** Build the draft-probe payload from form values (unsaved key included so
 * "Test connection" / "Discover models" use exactly what was typed). */
export function buildProbePayload(form: ProviderFormValues): ProviderProbePayload {
  const credential = form.apiKey.trim();
  return {
    type: form.type,
    name: form.name.trim() || undefined,
    base_url: form.baseUrl.trim() || null,
    model: form.model.trim() || undefined,
    ...(credential ? { credential } : {}),
  };
}

/** Sort providers for a stable list (default first, then by type). */
export function sortProviders(providers: ProviderSummary[]): ProviderSummary[] {
  return [...providers].sort((a, b) => {
    if (a.is_default !== b.is_default) {
      return a.is_default ? -1 : 1;
    }
    return a.type.localeCompare(b.type);
  });
}

/** Providers the Copilot selector can target: enabled only, stable order.
 * Disabled providers are excluded so a selection can never pin a provider
 * that is not ready to answer chat requests. */
export function selectableProviders(providers: ProviderSummary[]): ProviderSummary[] {
  return sortProviders(providers.filter((provider) => provider.enabled));
}

/** Chat request fields for the chosen provider.
 *
 * Maps a selected provider type to the ``provider``/``model`` fields the
 * existing chat API accepts. A stale or now-disabled selection falls back to
 * ``{ provider: null, model: null }`` so the backend's configured default is
 * used — an outdated selection can never pin a provider that no longer
 * exists. Selecting here never mutates the global default; the default is
 * only ever applied when the caller passes ``null``.
 *
 * ``modelOverride`` is a per-message manual model choice from the Copilot's
 * model picker. When non-empty it overrides the provider's configured model
 * for the next request; an empty override uses the provider's configured
 * model. Switching providers resets the override so the model follows the
 * selected provider's configuration.
 */
export function chatSelection(
  providers: ProviderSummary[],
  providerType: string | null,
  modelOverride: string | null = null,
): { provider: string | null; model: string | null } {
  const selected = providers.find((provider) => provider.type === providerType);
  if (!selected || !selected.enabled) {
    return { provider: null, model: null };
  }
  const override = modelOverride?.trim();
  return {
    provider: selected.type,
    model: override ? override : selected.model || null,
  };
}

/** Extract a human-readable error from a non-OK response. */
export async function apiErrorMessage(res: Response): Promise<string> {
  try {
    const data = (await res.json()) as { detail?: unknown };
    if (typeof data.detail === "string") {
      return data.detail;
    }
    if (Array.isArray(data.detail)) {
      return data.detail.map((item) => String(item)).join("; ");
    }
  } catch {
    // Non-JSON body — fall through to the status-based message.
  }
  return `Request failed with status ${res.status}`;
}

async function getJson<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { headers: authHeaders() });
  if (!res.ok) {
    throw new Error(await apiErrorMessage(res));
  }
  return (await res.json()) as T;
}

async function sendJson<T>(path: string, method: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(await apiErrorMessage(res));
  }
  return (await res.json()) as T;
}

/** List every configured provider (enabled and disabled). Read-only. */
export function listProviders(): Promise<ProviderListResponse> {
  return getJson<ProviderListResponse>("/providers");
}

/** List the provider types a caller can configure. Read-only. */
export function fetchProviderTypes(): Promise<ProviderTypesResponse> {
  return getJson<ProviderTypesResponse>("/providers/types");
}

/** Add a provider (admin/write scope). */
export function createProvider(body: Record<string, unknown>): Promise<ProviderSummary> {
  return sendJson<ProviderSummary>("/providers", "POST", body);
}

/** Edit a provider in place (admin/write scope). */
export function updateProvider(
  type: string,
  body: Record<string, unknown>,
): Promise<ProviderSummary> {
  return sendJson<ProviderSummary>(`/providers/${encodeURIComponent(type)}`, "PATCH", body);
}

/** Remove a provider (admin/write scope). */
export async function deleteProvider(type: string): Promise<{ deleted: boolean }> {
  const res = await fetch(`${API_BASE_URL}/providers/${encodeURIComponent(type)}`, {
    method: "DELETE",
    headers: authHeaders(),
  });
  if (!res.ok) {
    throw new Error(await apiErrorMessage(res));
  }
  return (await res.json()) as { deleted: boolean };
}

/** Enable a provider (admin/write scope). */
export function enableProvider(type: string): Promise<ProviderSummary> {
  return sendJson<ProviderSummary>(`/providers/${encodeURIComponent(type)}/enable`, "POST");
}

/** Disable a provider (admin/write scope). */
export function disableProvider(type: string): Promise<ProviderSummary> {
  return sendJson<ProviderSummary>(`/providers/${encodeURIComponent(type)}/disable`, "POST");
}

/** Set the default provider for unqualified AI calls (admin/write scope). */
export function setDefaultProvider(type: string): Promise<{ default_provider: string }> {
  return sendJson<{ default_provider: string }>("/providers/default", "POST", { type });
}

/** Remove a provider's stored credential without deleting the provider
 * (admin/write scope). Explicit removal — an empty key on edit keeps it. */
export function removeProviderCredential(type: string): Promise<{ removed: boolean }> {
  return sendJson<{ removed: boolean }>(
    `/providers/${encodeURIComponent(type)}/credential`,
    "DELETE",
  );
}

/** Probe a saved provider's connectivity by running a real model completion
 * (admin/write scope). Uses the stored credential. */
export function testProviderConnection(type: string): Promise<ProviderTestResult> {
  return sendJson<ProviderTestResult>(`/providers/${encodeURIComponent(type)}/test`, "POST");
}

/** Test a draft provider configuration (real model completion, categorized).
 * The unsaved ``credential`` typed in the form is used for this exact request;
 * it is never stored or returned. */
export function testProviderConfig(payload: ProviderProbePayload): Promise<ProviderTestResult> {
  return sendJson<ProviderTestResult>("/providers/test", "POST", payload);
}

/** List models served by a draft provider configuration so the UI can populate
 * a model dropdown; manual entry remains the fallback. Uses the unsaved
 * ``credential`` when one was typed. */
export function discoverProviderModels(payload: ProviderProbePayload): Promise<ModelDiscoveryResult> {
  return sendJson<ModelDiscoveryResult>("/providers/discover-models", "POST", payload);
}

/** Human-readable label for a connection-test failure category. */
export function providerTestCategoryLabel(category: ProviderTestCategory): string {
  switch (category) {
    case "ok":
      return "Connection OK";
    case "endpoint_unreachable":
      return "Endpoint unreachable";
    case "authentication_failed":
      return "Authentication failed";
    case "model_not_found":
      return "Model not found";
    case "rate_limited":
      return "Rate limited";
    case "provider_rejected":
      return "Provider rejected the request";
    case "timeout":
      return "Timed out";
    case "invalid_configuration":
      return "Invalid configuration";
  }
}
