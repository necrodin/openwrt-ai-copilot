"use client";

import { Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { DnsHost } from "@/lib/router-management";
import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/router/confirm-dialog";

type Props = {
  hosts: DnsHost[];
  busy?: boolean;
  onAdd: (hostname: string, ip: string) => void;
  onRemove: (host: DnsHost) => void;
};

type FormState = {
  hostname: string;
  ip: string;
} | null;

export function DnsHosts({ hosts, busy = false, onAdd, onRemove }: Props) {
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<FormState>(null);
  const [toDelete, setToDelete] = useState<DnsHost | null>(null);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) {
      return hosts;
    }
    return hosts.filter((host) =>
      [host.hostname, host.ip].some((value) => value.toLowerCase().includes(needle)),
    );
  }, [hosts, search]);

  const canSave = Boolean(form?.hostname.trim() && form?.ip.trim() && !busy);

  const save = () => {
    if (!form || !canSave) {
      return;
    }
    onAdd(form.hostname.trim(), form.ip.trim());
    setForm(null);
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="relative w-full md:max-w-sm">
          <Search
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            placeholder="Search hosts…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9 pr-8"
            aria-label="Search static hosts"
          />
          {search ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="absolute top-0 right-0 size-9"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <X className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
        <Button type="button" onClick={() => setForm({ hostname: "", ip: "" })} disabled={busy}>
          <Plus className="size-4" aria-hidden />
          Add host
        </Button>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-xl border py-10">
          <EmptyState
            message={
              hosts.length === 0
                ? "No static hosts configured."
                : "No hosts match your search."
            }
          />
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((host) => (
            <li
              key={`${host.hostname}-${host.ip}`}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border px-4 py-3"
            >
              <div className="min-w-0 space-y-1">
                <span className="block truncate text-sm font-medium">{host.hostname}</span>
                <p className="text-xs text-muted-foreground">
                  <span className="font-mono">{host.ip}</span>
                </p>
              </div>
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => setToDelete(host)}
                aria-label={`Delete ${host.hostname}`}
              >
                <Trash2 className="size-4" aria-hidden />
                Delete
              </Button>
            </li>
          ))}
        </ul>
      )}

      {form ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Add static host"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        >
          <div className="w-full max-w-md rounded-lg border bg-background p-5 shadow-lg">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">Add static host</h2>
                <p className="text-sm text-muted-foreground">
                  Pin a hostname to a fixed IP address for local resolution.
                </p>
              </div>
              <Button
                type="button"
                variant="ghost"
                size="icon"
                onClick={() => setForm(null)}
                aria-label="Close"
              >
                <X className="size-4" aria-hidden />
              </Button>
            </div>

            <div className="space-y-4">
              <div className="space-y-1.5">
                <Label htmlFor="hostname">Hostname</Label>
                <Input
                  id="hostname"
                  value={form.hostname}
                  onChange={(event) => setForm({ ...form, hostname: event.target.value })}
                  placeholder="nas"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ip">IP address</Label>
                <Input
                  id="ip"
                  value={form.ip}
                  onChange={(event) => setForm({ ...form, ip: event.target.value })}
                  placeholder="192.168.1.100"
                />
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setForm(null)}>
                Cancel
              </Button>
              <Button type="button" onClick={save} disabled={!canSave}>
                Add host
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={toDelete !== null}
        title={`Delete \u201c${toDelete?.hostname ?? "host"}\u201d?`}
        description="This static host entry will be removed from the resolver configuration. The name falls back to dynamic resolution."
        confirmLabel="Delete"
        busy={busy}
        onConfirm={() => {
          if (toDelete) {
            onRemove(toDelete);
          }
          setToDelete(null);
        }}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}
