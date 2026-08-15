"use client";

import { Bot, KeyRound, Loader2, Pencil, Plug, Plus, Power, Star, Trash2 } from "lucide-react";
import { useCallback, useEffect, useMemo, useState } from "react";

import { useAuth } from "@/components/auth/auth-boundary";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  buildCreatePayload,
  buildProbePayload,
  buildUpdatePayload,
  canMutateProviders,
  createProvider,
  defaultBaseUrl,
  deleteProvider,
  disableProvider,
  discoverProviderModels,
  editFormValues,
  emptyFormValues,
  enableProvider,
  fetchProviderTypes,
  listProviders,
  providerTestCategoryLabel,
  removeProviderCredential,
  setDefaultProvider,
  sortProviders,
  testProviderConfig,
  testProviderConnection,
  updateProvider,
  type ProviderFormValues,
  type ProviderModel,
  type ProviderSummary,
  type ProviderTestResult,
  type ProviderTypeInfo,
} from "@/lib/providers";

type Notice = { kind: "success" | "error"; message: string } | null;

type TestResult = { type: string; result: ProviderTestResult } | null;

type BusyState = { type: string; action: string } | null;

type ProbeBusy = "test" | "discover" | null;

const selectClasses =
  "h-9 w-full rounded-md border bg-background px-3 text-sm text-foreground shadow-xs";

/**
 * "AI Providers" section of the Settings page.
 *
 * Renders the configured providers (enabled and disabled), their default /
 * credential / enable state, and — for admin operators — full management:
 * add, edit, delete (with confirmation), enable/disable, set default, and a
 * connection test. Read-only operators can inspect the same information but
 * the mutation controls are hidden (the backend independently enforces 403).
 *
 * API-key credentials are referenced by environment-variable name; the key
 * value itself never leaves the operator's environment, and the edit form
 * leaves the field empty to preserve an existing credential.
 */
export function AiProvidersSection() {
  const auth = useAuth();
  const canMutate = canMutateProviders(auth.role);

  const [providers, setProviders] = useState<ProviderSummary[] | null>(null);
  const [types, setTypes] = useState<ProviderTypeInfo[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [form, setForm] = useState<ProviderFormValues | null>(null);
  const [formEditingType, setFormEditingType] = useState<string | null>(null);
  const [formBusy, setFormBusy] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const [confirmDelete, setConfirmDelete] = useState<ProviderSummary | null>(null);
  const [deleteBusy, setDeleteBusy] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [busy, setBusy] = useState<BusyState>(null);
  const [testResult, setTestResult] = useState<TestResult>(null);
  const [notice, setNotice] = useState<Notice>(null);

  // Draft-configuration diagnostics (test + model discovery) inside the form.
  const [probeBusy, setProbeBusy] = useState<ProbeBusy>(null);
  const [probeResult, setProbeResult] = useState<ProviderTestResult | null>(null);
  const [modelOptions, setModelOptions] = useState<ProviderModel[]>([]);
  const [modelMode, setModelMode] = useState<"manual" | "dropdown">("manual");

  const reload = useCallback(async () => {
    setLoadError(null);
    try {
      const [list, typeList] = await Promise.all([listProviders(), fetchProviderTypes()]);
      setProviders(list.providers);
      setTypes(typeList.types);
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    }
  }, []);

  useEffect(() => {
    void reload();
  }, [reload]);

  const sorted = useMemo(() => sortProviders(providers ?? []), [providers]);

  // True while editing a provider whose credential is already configured, so
  // the form can show "Credential configured" and never imply it is lost.
  const existingCredential =
    providers?.find((provider) => provider.type === formEditingType)?.has_credential ?? false;

  // Whether the chosen provider type requires an explicit base URL (e.g. the
  // always-available "Custom / OpenAI-compatible" option).
  const typeRequiresBaseUrl = (type: string): boolean => {
    const info = types.find((entry) => entry.type === type);
    return info?.requires_base_url ?? type === "compat";
  };

  const clearTransient = () => {
    setNotice(null);
    setTestResult(null);
    setFormError(null);
    setDeleteError(null);
  };

  const resetProbe = () => {
    setProbeBusy(null);
    setProbeResult(null);
    setModelOptions([]);
    setModelMode("manual");
  };

  const openCreate = () => {
    clearTransient();
    resetProbe();
    setForm(emptyFormValues());
    setFormEditingType(null);
  };

  const openEdit = (provider: ProviderSummary) => {
    clearTransient();
    resetProbe();
    setForm(editFormValues(provider));
    setFormEditingType(provider.type);
  };

  const closeForm = () => {
    setForm(null);
    setFormEditingType(null);
    setFormBusy(false);
    setFormError(null);
    resetProbe();
  };

  const saveForm = async () => {
    if (!form) {
      return;
    }
    if (formEditingType === null && !form.type) {
      setFormError("Choose a provider type.");
      return;
    }
    setFormBusy(true);
    setFormError(null);
    try {
      if (formEditingType === null) {
        await createProvider(buildCreatePayload(form));
        setNotice({ kind: "success", message: `Provider "${form.type}" added.` });
      } else {
        const existing = providers?.find((provider) => provider.type === formEditingType);
        if (!existing) {
          throw new Error(`Provider "${formEditingType}" no longer exists.`);
        }
        await updateProvider(formEditingType, buildUpdatePayload(form));
        setNotice({ kind: "success", message: `Provider "${formEditingType}" saved.` });
      }
      setForm(null);
      setFormEditingType(null);
      await reload();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    } finally {
      setFormBusy(false);
    }
  };

  const runAction = async (provider: ProviderSummary, action: string) => {
    clearTransient();
    setBusy({ type: provider.type, action });
    try {
      switch (action) {
        case "enable":
          await enableProvider(provider.type);
          break;
        case "disable":
          await disableProvider(provider.type);
          break;
        case "default":
          await setDefaultProvider(provider.type);
          break;
        case "remove-credential":
          await removeProviderCredential(provider.type);
          setNotice({ kind: "success", message: `Credential removed from "${provider.name}".` });
          break;
        case "test":
          const result = await testProviderConnection(provider.type);
          setTestResult({ type: provider.type, result });
          break;
      }
      if (action !== "test") {
        await reload();
      }
    } catch (error) {
      setNotice({ kind: "error", message: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(null);
    }
  };

  const removeCredentialFromForm = async () => {
    if (!form || formEditingType === null) {
      return;
    }
    setFormBusy(true);
    setFormError(null);
    try {
      await removeProviderCredential(formEditingType);
      setForm({ ...form, apiKey: "" });
      setNotice({ kind: "success", message: "Credential removed." });
      await reload();
    } catch (error) {
      setFormError(error instanceof Error ? error.message : String(error));
    } finally {
      setFormBusy(false);
    }
  };

  const confirmDeleteProvider = async () => {
    if (!confirmDelete) {
      return;
    }
    setDeleteBusy(true);
    setDeleteError(null);
    try {
      await deleteProvider(confirmDelete.type);
      setConfirmDelete(null);
      setNotice({ kind: "success", message: `Provider "${confirmDelete.type}" deleted.` });
      await reload();
    } catch (error) {
      setDeleteError(error instanceof Error ? error.message : String(error));
    } finally {
      setDeleteBusy(false);
    }
  };

  const selectType = (type: string) => {
    resetProbe();
    setForm((current) =>
      current
        ? { ...current, type, baseUrl: defaultBaseUrl(types, type) }
        : current,
    );
  };

  const runFormTest = async () => {
    if (!form || probeBusy) {
      return;
    }
    if (!form.type) {
      setProbeResult({
        ok: false,
        category: "invalid_configuration",
        message: "Choose a provider type first.",
      });
      return;
    }
    setProbeBusy("test");
    setProbeResult(null);
    try {
      const result = await testProviderConfig(buildProbePayload(form));
      setProbeResult(result);
    } catch (error) {
      setProbeResult({
        ok: false,
        category: "invalid_configuration",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setProbeBusy(null);
    }
  };

  const runModelDiscovery = async () => {
    if (!form || probeBusy) {
      return;
    }
    if (!form.type) {
      setProbeResult({
        ok: false,
        category: "invalid_configuration",
        message: "Choose a provider type first.",
      });
      return;
    }
    setProbeBusy("discover");
    setProbeResult(null);
    try {
      const result = await discoverProviderModels(buildProbePayload(form));
      if (result.ok && result.models && result.models.length > 0) {
        setModelOptions(result.models);
        setModelMode("dropdown");
        setForm((current) =>
          current && !current.model.trim() ? { ...current, model: result.models![0].id } : current,
        );
      } else {
        setProbeResult({
          ok: false,
          category: result.category ?? "provider_rejected",
          message: result.message ?? "Model discovery is unavailable for this endpoint.",
        });
      }
    } catch (error) {
      setProbeResult({
        ok: false,
        category: "provider_rejected",
        message: error instanceof Error ? error.message : String(error),
      });
    } finally {
      setProbeBusy(null);
    }
  };

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold">AI Providers</h2>
          <p className="text-sm text-muted-foreground">
            Which AI backend the Copilot uses and how it is reached.
          </p>
        </div>
        {canMutate ? (
          <Button size="sm" variant="outline" onClick={openCreate}>
            <Plus className="size-4" aria-hidden />
            Add provider
          </Button>
        ) : null}
      </div>

      {notice ? (
        <p
          role="status"
          className={
            notice.kind === "error"
              ? "text-sm text-destructive"
              : "text-sm text-emerald-700 dark:text-emerald-400"
          }
        >
          {notice.message}
        </p>
      ) : null}

      {form ? (
        <Card>
          <CardContent className="space-y-4 pt-6">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <div className="space-y-1.5">
                <Label htmlFor="provider-type">Provider type</Label>
                {formEditingType === null ? (
                  <select
                    id="provider-type"
                    className={selectClasses}
                    value={form.type}
                    onChange={(event) => selectType(event.target.value)}
                  >
                    <option value="" disabled>
                      Select a provider…
                    </option>
                    {types.map((type) => (
                      <option key={type.type} value={type.type}>
                        {type.label}
                      </option>
                    ))}
                  </select>
                ) : (
                  <Input id="provider-type" value={form.type} disabled aria-readonly />
                )}
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="provider-name">Name</Label>
                <Input
                  id="provider-name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                  placeholder="My provider"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="provider-base-url">Base URL</Label>
                <Input
                  id="provider-base-url"
                  value={form.baseUrl}
                  onChange={(event) => setForm({ ...form, baseUrl: event.target.value })}
                  placeholder={
                    typeRequiresBaseUrl(form.type)
                      ? "https://your-endpoint.example.com/v1 (required)"
                      : "https://api.example.com/v1"
                  }
                  inputMode="url"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <Label htmlFor="provider-model">Model</Label>
                {modelMode === "dropdown" && modelOptions.length > 0 ? (
                  <div className="flex items-center gap-2">
                    <select
                      id="provider-model"
                      className={selectClasses}
                      value={form.model}
                      onChange={(event) => setForm({ ...form, model: event.target.value })}
                    >
                      {form.model &&
                      !modelOptions.some((option) => option.id === form.model) ? (
                        <option value={form.model}>Custom: {form.model}</option>
                      ) : null}
                      {modelOptions.map((option) => (
                        <option key={option.id} value={option.id}>
                          {option.id}
                        </option>
                      ))}
                    </select>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      className="shrink-0"
                      onClick={() => setModelMode("manual")}
                    >
                      Manual
                    </Button>
                  </div>
                ) : (
                  <div className="flex items-center gap-2">
                    <Input
                      id="provider-model"
                      className="flex-1"
                      value={form.model}
                      onChange={(event) => setForm({ ...form, model: event.target.value })}
                      placeholder="gpt-4o-mini"
                    />
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      disabled={probeBusy !== null}
                      onClick={() => void runModelDiscovery()}
                    >
                      {probeBusy === "discover" ? (
                        <Loader2 className="size-4 animate-spin" aria-hidden />
                      ) : null}
                      Discover models
                    </Button>
                  </div>
                )}
                <p className="text-xs text-muted-foreground">
                  Discover models from the endpoint, or type one manually.
                </p>
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <div className="flex items-center justify-between gap-2">
                  <Label htmlFor="provider-api-key">API Key</Label>
                  {formEditingType !== null && existingCredential ? (
                    <span className="text-xs font-medium text-emerald-700 dark:text-emerald-400">
                      Credential configured
                    </span>
                  ) : null}
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    id="provider-api-key"
                    type="password"
                    className="flex-1"
                    value={form.apiKey}
                    onChange={(event) => setForm({ ...form, apiKey: event.target.value })}
                    placeholder={
                      formEditingType === null
                        ? "Enter API key"
                        : existingCredential
                          ? "Leave empty to keep the current credential"
                          : "Enter API key"
                    }
                    autoComplete="new-password"
                    spellCheck={false}
                  />
                  {formEditingType !== null && existingCredential ? (
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0"
                      disabled={formBusy}
                      onClick={() => void removeCredentialFromForm()}
                    >
                      Remove credential
                    </Button>
                  ) : null}
                </div>
                <p className="text-xs text-muted-foreground">
                  The API key is encrypted on the server and never returned to or
                  stored by this app. Leaving it empty keeps the current
                  credential; entering a new key replaces it.
                </p>
              </div>
              <div className="flex flex-wrap items-center gap-2 sm:col-span-2">
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  disabled={probeBusy !== null}
                  onClick={() => void runFormTest()}
                >
                  {probeBusy === "test" ? (
                    <Loader2 className="size-4 animate-spin" aria-hidden />
                  ) : (
                    <Plug className="size-4" aria-hidden />
                  )}
                  Test connection
                </Button>
                <span className="text-xs text-muted-foreground">
                  Verifies the endpoint, credential, and model with a minimal
                  completion.
                </span>
              </div>
              {probeResult ? (
                <p
                  role={probeResult.ok ? "status" : "alert"}
                  className={
                    probeResult.ok
                      ? "text-sm text-emerald-700 dark:text-emerald-400"
                      : "text-sm text-destructive"
                  }
                >
                  {providerTestCategoryLabel(probeResult.category)} — {probeResult.message}
                </p>
              ) : null}
              <div className="flex items-center gap-2 sm:col-span-2">
                <input
                  id="provider-enabled"
                  type="checkbox"
                  checked={form.enabled}
                  onChange={(event) => setForm({ ...form, enabled: event.target.checked })}
                  className="size-4 rounded border-border accent-primary"
                />
                <Label htmlFor="provider-enabled">Enabled</Label>
              </div>
            </div>

            {formError ? (
              <p className="text-sm text-destructive" role="alert">
                {formError}
              </p>
            ) : null}

            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={closeForm} disabled={formBusy}>
                Cancel
              </Button>
              <Button type="button" onClick={() => void saveForm()} disabled={formBusy}>
                {formBusy ? <Loader2 className="size-4 animate-spin" aria-hidden /> : null}
                {formBusy ? "Saving…" : "Save provider"}
              </Button>
            </div>
          </CardContent>
        </Card>
      ) : null}

      <Card>
        <CardContent className="space-y-2 pt-6">
          {loadError ? (
            <p className="text-sm text-destructive" role="alert">
              Could not load providers: {loadError}
            </p>
          ) : providers === null ? (
            <p className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" aria-hidden />
              Loading providers…
            </p>
          ) : sorted.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No providers are configured yet. The Copilot will have no AI
              backend until at least one provider is added.
            </p>
          ) : (
            <ul className="divide-y">
              {sorted.map((provider) => (
                <li
                  key={provider.type}
                  className="flex flex-wrap items-center justify-between gap-3 py-3"
                >
                  <div className="flex min-w-0 items-center gap-3">
                    <Bot className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                    <div className="min-w-0 space-y-1">
                      <p className="flex flex-wrap items-center gap-1.5">
                        <span className="truncate text-sm font-medium">{provider.name}</span>
                        <Badge variant="outline">{provider.type}</Badge>
                        {provider.is_default ? (
                          <Badge variant="default">
                            <Star className="size-3" aria-hidden />
                            Default
                          </Badge>
                        ) : null}
                        {provider.has_credential ? (
                          <Badge variant="secondary">Credential configured</Badge>
                        ) : null}
                      </p>
                      <p className="text-xs text-muted-foreground">
                        {provider.model || "No model set"}
                        <span className="mx-1" aria-hidden>
                          ·
                        </span>
                        <span className="break-all">{provider.base_url}</span>
                      </p>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center justify-end gap-2">
                    <StatusBadge
                      label={provider.enabled ? "Enabled" : "Disabled"}
                      tone={provider.enabled ? "success" : "neutral"}
                    />
                    {testResult?.type === provider.type ? (
                      <StatusBadge
                        label={providerTestCategoryLabel(testResult.result.category)}
                        tone={testResult.result.ok ? "success" : "danger"}
                      />
                    ) : null}
                    {canMutate ? (
                      <>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busy?.type === provider.type}
                          onClick={() => void runAction(provider, "test")}
                        >
                          {busy?.type === provider.type && busy.action === "test" ? (
                            <Loader2 className="size-4 animate-spin" aria-hidden />
                          ) : (
                            <Plug className="size-4" aria-hidden />
                          )}
                          Test
                        </Button>
                        {!provider.is_default && provider.enabled ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy?.type === provider.type}
                            onClick={() => void runAction(provider, "default")}
                          >
                            {busy?.type === provider.type && busy.action === "default" ? (
                              <Loader2 className="size-4 animate-spin" aria-hidden />
                            ) : (
                              <Star className="size-4" aria-hidden />
                            )}
                            Set default
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busy?.type === provider.type}
                          onClick={() => void runAction(provider, provider.enabled ? "disable" : "enable")}
                        >
                          {busy?.type === provider.type &&
                          (busy.action === "enable" || busy.action === "disable") ? (
                            <Loader2 className="size-4 animate-spin" aria-hidden />
                          ) : (
                            <Power className="size-4" aria-hidden />
                          )}
                          {provider.enabled ? "Disable" : "Enable"}
                        </Button>
                        {provider.has_credential ? (
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            disabled={busy?.type === provider.type}
                            onClick={() => void runAction(provider, "remove-credential")}
                          >
                            {busy?.type === provider.type &&
                            busy.action === "remove-credential" ? (
                              <Loader2 className="size-4 animate-spin" aria-hidden />
                            ) : (
                              <KeyRound className="size-4" aria-hidden />
                            )}
                            Remove credential
                          </Button>
                        ) : null}
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busy?.type === provider.type}
                          onClick={() => openEdit(provider)}
                        >
                          <Pencil className="size-4" aria-hidden />
                          Edit
                        </Button>
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          disabled={busy?.type === provider.type}
                          onClick={() => setConfirmDelete(provider)}
                        >
                          <Trash2 className="size-4" aria-hidden />
                          Delete
                        </Button>
                      </>
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirmDelete !== null}
        title={`Delete provider ${confirmDelete?.name ?? ""}?`}
        description={`This removes "${confirmDelete?.type ?? ""}" from the provider configuration. This cannot be undone.`}
        confirmLabel="Delete"
        busy={deleteBusy}
        error={deleteError}
        onConfirm={() => void confirmDeleteProvider()}
        onCancel={() => setConfirmDelete(null)}
      />
    </section>
  );
}
