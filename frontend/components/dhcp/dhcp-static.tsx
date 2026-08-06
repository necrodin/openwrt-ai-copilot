"use client";

import { Pencil, Plus, Search, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import type { DhcpHostInput } from "@/hooks/use-dhcp";
import type { DhcpStaticLease } from "@/lib/dashboard";
import { EmptyState } from "@/components/dashboard/widget";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/router/confirm-dialog";

type Props = {
  staticLeases: DhcpStaticLease[];
  busy?: boolean;
  onToggle: (lease: DhcpStaticLease, enabled: boolean) => void;
  onSave: (input: DhcpHostInput) => void;
  onDelete: (lease: DhcpStaticLease) => void;
};

type FormState = {
  mode: "add" | "edit";
  section?: string;
  hostname: string;
  ip: string;
  mac: string;
} | null;

const EMPTY_FORM = {
  hostname: "",
  ip: "",
  mac: "",
};

function normalizeMac(value: string): string {
  return value.trim().toUpperCase();
}

export function DhcpStaticLeases({
  staticLeases,
  busy = false,
  onToggle,
  onSave,
  onDelete,
}: Props) {
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<FormState>(null);
  const [toDelete, setToDelete] = useState<DhcpStaticLease | null>(null);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) {
      return staticLeases;
    }
    return staticLeases.filter((lease) =>
      [lease.hostname, lease.ip, lease.mac]
        .filter(Boolean)
        .some((value) => value?.toLowerCase().includes(needle)),
    );
  }, [staticLeases, search]);

  const openAdd = () => {
    setForm({ mode: "add", ...EMPTY_FORM });
  };

  const openEdit = (lease: DhcpStaticLease) => {
    setForm({
      mode: "edit",
      section: lease.section,
      hostname: lease.hostname ?? "",
      ip: lease.ip ?? "",
      mac: lease.mac ?? "",
    });
  };

  const save = () => {
    if (!form) {
      return;
    }
    const mac = normalizeMac(form.mac);
    const input: DhcpHostInput = {
      hostname: form.hostname.trim(),
      ip: form.ip.trim(),
      mac,
      section: form.section,
    };
    if (input.hostname && input.ip && input.mac) {
      onSave(input);
      setForm(null);
    }
  };

  const canSave = Boolean(
    form?.hostname.trim() && form?.ip.trim() && form?.mac.trim() && !busy,
  );

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
            placeholder="Search static leases…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="pl-9 pr-8"
            aria-label="Search static leases"
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
        <Button type="button" onClick={openAdd} disabled={busy}>
          <Plus className="size-4" aria-hidden />
          Add lease
        </Button>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-xl border py-10">
          <EmptyState
            message={
              staticLeases.length === 0
                ? "No static leases configured."
                : "No static leases match your search."
            }
          />
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((lease) => (
            <li
              key={lease.section}
              className={`rounded-md border px-4 py-3 ${lease.enabled ? "" : "opacity-60"}`}
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="truncate text-sm font-medium">
                      {lease.hostname || "Unnamed"}
                    </span>
                    <Badge variant={lease.enabled ? "default" : "secondary"}>
                      {lease.enabled ? "enabled" : "disabled"}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    <span className="font-mono">{lease.ip ?? "—"}</span>
                    <span className="mx-1.5">·</span>
                    <span className="font-mono">{lease.mac ?? "—"}</span>
                  </p>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    size="sm"
                    variant={lease.enabled ? "outline" : "default"}
                    disabled={busy}
                    onClick={() => onToggle(lease, !lease.enabled)}
                  >
                    {lease.enabled ? "Disable" : "Enable"}
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busy}
                    onClick={() => openEdit(lease)}
                    aria-label={`Edit ${lease.hostname ?? "lease"}`}
                  >
                    <Pencil className="size-4" aria-hidden />
                    Edit
                  </Button>
                  <Button
                    size="sm"
                    variant="destructive"
                    disabled={busy}
                    onClick={() => setToDelete(lease)}
                    aria-label={`Delete ${lease.hostname ?? "lease"}`}
                  >
                    <Trash2 className="size-4" aria-hidden />
                    Delete
                  </Button>
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}

      {form ? (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={form.mode === "add" ? "Add static lease" : "Edit static lease"}
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
        >
          <div className="w-full max-w-md rounded-lg border bg-background p-5 shadow-lg">
            <div className="mb-4 flex items-start justify-between gap-3">
              <div>
                <h2 className="text-lg font-semibold">
                  {form.mode === "add" ? "Add static lease" : "Edit static lease"}
                </h2>
                <p className="text-sm text-muted-foreground">
                  Reserve a fixed IP for a device by MAC address.
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
                  placeholder="my-device"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="ip">IP address</Label>
                <Input
                  id="ip"
                  value={form.ip}
                  onChange={(event) => setForm({ ...form, ip: event.target.value })}
                  placeholder="192.168.1.200"
                />
              </div>
              <div className="space-y-1.5">
                <Label htmlFor="mac">MAC address</Label>
                <Input
                  id="mac"
                  value={form.mac}
                  onChange={(event) => setForm({ ...form, mac: event.target.value })}
                  placeholder="aa:bb:cc:dd:ee:ff"
                />
              </div>
            </div>

            <div className="mt-5 flex justify-end gap-2">
              <Button type="button" variant="outline" onClick={() => setForm(null)}>
                Cancel
              </Button>
              <Button type="button" onClick={save} disabled={!canSave}>
                {form.mode === "add" ? "Add lease" : "Save changes"}
              </Button>
            </div>
          </div>
        </div>
      ) : null}

      <ConfirmDialog
        open={toDelete !== null}
        title={`Delete \u201c${toDelete?.hostname ?? "lease"}\u201d?`}
        description="This static lease will be removed. The device will fall back to the dynamic DHCP range on its next request."
        confirmLabel="Delete"
        busy={busy}
        onConfirm={() => {
          if (toDelete) {
            onDelete(toDelete);
          }
          setToDelete(null);
        }}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
}