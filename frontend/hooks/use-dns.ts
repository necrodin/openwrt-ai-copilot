"use client";

import { useCallback, useMemo, useState } from "react";

import {
  fetchDnsInfo,
  type DnsAction,
  type DnsInfo,
  type ManagementJob,
} from "@/lib/router-management";
import { useDashboardData } from "@/hooks/use-dashboard-data";
import { useManagementJob } from "@/hooks/use-management-job";
import { usePolling } from "@/hooks/use-polling";
import { filterInternalHosts, reconcileUpstream } from "@/lib/dns-utils";
import type { ConnectionStatus } from "@/lib/dashboard-utils";
import type { Source } from "@/lib/dashboard";

const DNS_POLL_MS = 10_000;

export type DnsNotice = { tone: "success" | "danger"; message: string };

export type DnsRunPayload = {
  server?: string;
  hostname?: string;
  ip?: string;
  enabled?: boolean;
};

export type DnsDataResult = {
  dns: DnsInfo | null;
  status: ConnectionStatus;
  loading: boolean;
  error: string | null;
  connected: boolean;
  source: Source | null;
  routerLabel: string;
  updatedAt: string | null;
  refetch: () => void;
  busy: boolean;
  job: ManagementJob | null;
  notice: DnsNotice | null;
  dismissNotice: () => void;
  run: (action: DnsAction, payload?: DnsRunPayload) => Promise<void>;
};

function describe(job: ManagementJob): string {
  const result = job.result as { message?: string } | null;
  return result?.message ?? job.message;
}

function message(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * DNS / dnsmasq forwarder configuration and management.
 *
 * Polls the management API for the live DNS inventory (upstream servers,
 * static hosts, domain) and routes every mutation (reload, restart, enable /
 * disable the service, add/remove upstream servers and static hosts) through
 * the tracked management job framework. After a successful change the
 * inventory is re-fetched so the UI reflects the new state immediately.
 */
export function useDns(): DnsDataResult {
  const dnsPoll = usePolling<DnsInfo>(
    useCallback((signal) => fetchDnsInfo(signal), []),
    { intervalMs: DNS_POLL_MS },
  );
  const { update, status } = useDashboardData();
  const runner = useManagementJob();
  const [notice, setNotice] = useState<DnsNotice | null>(null);

  const snapshotDns = update?.snapshot?.network_status?.dns ?? null;
  const dns = useMemo<DnsInfo | null>(() => {
    if (!dnsPoll.data) {
      return null;
    }
    const hosts = filterInternalHosts(dnsPoll.data.hosts);
    return {
      ...dnsPoll.data,
      upstream: reconcileUpstream(dnsPoll.data.upstream, snapshotDns),
      hosts,
      counts: { ...dnsPoll.data.counts, hosts: hosts.length },
    };
  }, [dnsPoll.data, snapshotDns]);
  const updatedAt = dnsPoll.data ? (update?.sent_at ?? null) : null;
  const routerLabel = update?.snapshot
    ? update.snapshot.meta.model || update.snapshot.meta.board || "router"
    : "router";

  const announce = useCallback((tone: DnsNotice["tone"], messageText: string) => {
    setNotice({ tone, message: messageText });
  }, []);

  const run = useCallback(
    async (action: DnsAction, payload: DnsRunPayload = {}) => {
      setNotice(null);
      try {
        const job = await runner.runDns(action, payload);
        announce(job.status === "succeeded" ? "success" : "danger", describe(job));
        if (job.status === "succeeded") {
          dnsPoll.refetch();
        }
      } catch (e) {
        announce("danger", message(e));
      }
    },
    [runner, announce, dnsPoll],
  );

  const dismissNotice = useCallback(() => setNotice(null), []);

  return {
    dns,
    status,
    loading: dnsPoll.loading,
    error: dnsPoll.error,
    connected: update?.connected ?? false,
    source: update?.source ?? null,
    routerLabel,
    updatedAt,
    refetch: dnsPoll.refetch,
    busy: runner.busy,
    job: runner.job,
    notice,
    dismissNotice,
    run,
  };
}