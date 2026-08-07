"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import {
  confirmJob,
  downloadJobArtifact,
  fetchJob,
  readFileAsBase64,
  saveSystemConfig,
  startJob,
  type DhcpHostPayload,
  type JobRequest,
  type ManagementJob,
  type NetworkAction,
  type SystemConfig,
} from "@/lib/router-management";

const TERMINAL_STATUSES = new Set(["succeeded", "failed"]);
const POLL_MS = 800;

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export type ManagementJobRunner = {
  job: ManagementJob | null;
  busy: boolean;
  error: string | null;
  runAction: (action: string) => Promise<ManagementJob>;
  runFirewallToggle: (section: string, enabled: boolean) => Promise<ManagementJob>;
  runWirelessToggle: (section: string, enabled: boolean) => Promise<ManagementJob>;
  runVpnToggle: (section: string, enabled: boolean) => Promise<ManagementJob>;
  setDhcpEnabled: (enabled: boolean) => Promise<ManagementJob>;
  addDhcpHost: (payload: DhcpHostPayload) => Promise<ManagementJob>;
  editDhcpHost: (payload: DhcpHostPayload) => Promise<ManagementJob>;
  deleteDhcpHost: (section: string) => Promise<ManagementJob>;
  toggleDhcpHost: (section: string, enabled: boolean) => Promise<ManagementJob>;
  runNetwork: (action: NetworkAction, section: string) => Promise<ManagementJob>;
  saveSystem: (config: SystemConfig) => Promise<ManagementJob>;
  createBackup: () => Promise<ManagementJob>;
  createBundle: () => Promise<ManagementJob>;
  stageRestore: (file: File) => Promise<ManagementJob>;
  confirmRestore: (jobId: string) => Promise<ManagementJob>;
  downloadArtifact: (job: ManagementJob) => Promise<void>;
  reset: () => void;
};

/**
 * Orchestrates management jobs: starts them (or confirms a staged restore),
 * polls until they finish, and surfaces progress + errors to the UI. One
 * runner per panel keeps the state machine simple — a single operation runs at
 * a time, so the panel never issues overlapping destructive commands.
 */
export function useManagementJob(): ManagementJobRunner {
  const [job, setJob] = useState<ManagementJob | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const active = useRef(false);

  useEffect(() => {
    return () => {
      active.current = false;
    };
  }, []);

  const fail = useCallback((e: unknown) => {
    setError(message(e));
    setBusy(false);
  }, []);

  const pollUntilTerminal = useCallback(async (first: ManagementJob): Promise<ManagementJob> => {
    let current = first;
    while (active.current && !TERMINAL_STATUSES.has(current.status)) {
      await sleep(POLL_MS);
      if (!active.current) {
        break;
      }
      current = await fetchJob(current.id);
      if (!active.current) {
        break;
      }
      setJob(current);
      setError(current.error);
    }
    return current;
  }, []);

  const begin = useCallback(
    async (payload: JobRequest, poll: boolean): Promise<ManagementJob> => {
      active.current = true;
      setError(null);
      setBusy(true);
      setJob(null);
      try {
        const created = await startJob(payload);
        if (!active.current) {
          return created;
        }
        setJob(created);
        if (!poll) {
          setBusy(false);
          return created;
        }
        const finished = await pollUntilTerminal(created);
        if (!active.current) {
          return finished;
        }
        setBusy(false);
        if (finished.error) {
          throw new Error(finished.error);
        }
        if (finished.status === "failed") {
          throw new Error(finished.message);
        }
        return finished;
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [fail, pollUntilTerminal],
  );

  const runAction = useCallback(
    (action: string) => begin({ kind: "action", action, confirmed: true }, true),
    [begin],
  );

  const runFirewallToggle = useCallback(
    (section: string, enabled: boolean) =>
      begin({ kind: "firewall", section, enabled, confirmed: true }, true),
    [begin],
  );

  const runWirelessToggle = useCallback(
    (section: string, enabled: boolean) =>
      begin({ kind: "wireless", section, enabled, confirmed: true }, true),
    [begin],
  );

  const runVpnToggle = useCallback(
    (section: string, enabled: boolean) =>
      begin({ kind: "vpn", section, enabled, confirmed: true }, true),
    [begin],
  );

  const setDhcpEnabled = useCallback(
    (enabled: boolean) => begin({ kind: "dhcp", action: "set-enabled", enabled, confirmed: true }, true),
    [begin],
  );

  const addDhcpHost = useCallback(
    (payload: DhcpHostPayload) =>
      begin({ kind: "dhcp", action: "host-add", confirmed: true, ...payload }, true),
    [begin],
  );

  const editDhcpHost = useCallback(
    (payload: DhcpHostPayload) =>
      begin({ kind: "dhcp", action: "host-edit", confirmed: true, ...payload }, true),
    [begin],
  );

  const deleteDhcpHost = useCallback(
    (section: string) =>
      begin({ kind: "dhcp", action: "host-delete", section, confirmed: true }, true),
    [begin],
  );

  const toggleDhcpHost = useCallback(
    (section: string, enabled: boolean) =>
      begin({ kind: "dhcp", action: "host-toggle", section, enabled, confirmed: true }, true),
    [begin],
  );

  const runNetwork = useCallback(
    (action: NetworkAction, section: string) =>
      begin({ kind: "network", action, section, confirmed: true }, true),
    [begin],
  );

  const saveSystem = useCallback(
    (config: SystemConfig) => saveSystemConfig(config),
    [],
  );

  const createBackup = useCallback(() => begin({ kind: "backup", confirmed: false }, true), [begin]);

  const createBundle = useCallback(() => begin({ kind: "bundle", confirmed: false }, true), [begin]);

  const stageRestore = useCallback(
    async (file: File) => {
      active.current = true;
      setError(null);
      setBusy(true);
      setJob(null);
      try {
        const content_b64 = await readFileAsBase64(file);
        const created = await startJob({
          kind: "restore",
          filename: file.name,
          content_b64,
          confirmed: false,
        });
        if (active.current) {
          setJob(created);
          setBusy(false);
        }
        return created;
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [fail],
  );

  const confirmRestore = useCallback(
    async (jobId: string) => {
      active.current = true;
      setError(null);
      setBusy(true);
      try {
        await confirmJob(jobId);
        const staged = (await fetchJob(jobId)) as ManagementJob;
        const finished = await pollUntilTerminal(staged);
        if (!active.current) {
          return finished;
        }
        setJob(finished);
        setBusy(false);
        if (finished.error) {
          throw new Error(finished.error);
        }
        if (finished.status === "failed") {
          throw new Error(finished.message);
        }
        return finished;
      } catch (e) {
        fail(e);
        throw e;
      }
    },
    [fail, pollUntilTerminal],
  );

  const downloadArtifact = useCallback(async (target: ManagementJob) => {
    await downloadJobArtifact(target.id, target.artifact?.name);
  }, []);

  const reset = useCallback(() => {
    active.current = false;
    setJob(null);
    setBusy(false);
    setError(null);
  }, []);

  return {
    job,
    busy,
    error,
    runAction,
    runFirewallToggle,
    runWirelessToggle,
    runVpnToggle,
    setDhcpEnabled,
    addDhcpHost,
    editDhcpHost,
    deleteDhcpHost,
    toggleDhcpHost,
    runNetwork,
    saveSystem,
    createBackup,
    createBundle,
    stageRestore,
    confirmRestore,
    downloadArtifact,
    reset,
  };
}