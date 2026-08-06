"use client";

import { useCallback, useState } from "react";

import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { DhcpStaticLease, DhcpInfo, Source } from "@/lib/dashboard";

export type DhcpNotice = { tone: "success" | "danger"; message: string };

export type DhcpHostInput = {
  section?: string;
  hostname: string;
  ip: string;
  mac: string;
};

export type DhcpDataResult = {
  dhcp: DhcpInfo | null;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
  busy: boolean;
  notice: DhcpNotice | null;
  dismissNotice: () => void;
  setEnabled: (enabled: boolean) => Promise<void>;
  reload: () => Promise<void>;
  restart: () => Promise<void>;
  addHost: (input: DhcpHostInput) => Promise<void>;
  editHost: (input: DhcpHostInput) => Promise<void>;
  deleteHost: (lease: DhcpStaticLease) => Promise<void>;
  toggleHost: (lease: DhcpStaticLease, enabled: boolean) => Promise<void>;
};

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function jobMessage(job: { status: string; result: unknown; message: string }, fallback: string): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message ?? fallback;
}

/**
 * DHCP server, active leases, static leases and management for the dashboard.
 *
 * Consumes the polling dashboard snapshot for dnsmasq state and exposes the
 * real management actions (enable/disable the server, restart/reload, and
 * static lease CRUD) through the backend management job service over SSH. A
 * successful change triggers an immediate refetch so the UI tracks reality.
 */
export function useDhcp(): DhcpDataResult {
  const { update, status, loading, error, refetch } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<DhcpNotice | null>(null);

  const snapshot = update?.snapshot ?? null;
  const dhcp = snapshot?.dhcp ?? null;
  const updatedAt = update?.sent_at ?? null;

  const routerLabel = snapshot
    ? snapshot.meta.model || snapshot.meta.board || "router"
    : "router";

  const announce = useCallback((tone: DhcpNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const setEnabled = useCallback(
    async (enabled: boolean) => {
      setNotice(null);
      try {
        const job = await runner.setDhcpEnabled(enabled);
        announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "DHCP server updated."));
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetch],
  );

  const reload = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("reload-dhcp");
      announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "DHCP reloaded."));
      if (job.status === "succeeded") {
        refetch();
      }
    } catch (e) {
      announce("danger", message(e));
    }
  }, [runner, announce, refetch]);

  const restart = useCallback(async () => {
    setNotice(null);
    try {
      const job = await runner.runAction("restart-dhcp");
      announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "DHCP restarted."));
      if (job.status === "succeeded") {
        refetch();
      }
    } catch (e) {
      announce("danger", message(e));
    }
  }, [runner, announce, refetch]);

  const addHost = useCallback(
    async (input: DhcpHostInput) => {
      setNotice(null);
      try {
        const job = await runner.addDhcpHost(input);
        announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "Static lease added."));
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetch],
  );

  const editHost = useCallback(
    async (input: DhcpHostInput) => {
      setNotice(null);
      try {
        const job = await runner.editDhcpHost(input);
        announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "Static lease updated."));
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetch],
  );

  const deleteHost = useCallback(
    async (lease: DhcpStaticLease) => {
      setNotice(null);
      try {
        const job = await runner.deleteDhcpHost(lease.section);
        announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "Static lease deleted."));
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetch],
  );

  const toggleHost = useCallback(
    async (lease: DhcpStaticLease, enabled: boolean) => {
      setNotice(null);
      try {
        const job = await runner.toggleDhcpHost(lease.section, enabled);
        announce(job.status === "succeeded" ? "success" : "danger", jobMessage(job, "Static lease updated."));
        if (job.status === "succeeded") {
          refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, refetch],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    dhcp,
    status,
    loading,
    error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    refetch,
    busy: runner.busy,
    notice,
    dismissNotice,
    setEnabled,
    reload,
    restart,
    addHost,
    editHost,
    deleteHost,
    toggleHost,
  };
}