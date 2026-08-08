"use client";

import { Plus, Trash2, X } from "lucide-react";
import { useMemo, useState } from "react";

import { EmptyState } from "@/components/dashboard/widget";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { ConfirmDialog } from "@/components/router/confirm-dialog";

type Props = {
  servers: string[];
  busy?: boolean;
  onAdd: (server: string) => void;
  onRemove: (server: string) => void;
};

export function DnsServers({ servers, busy = false, onAdd, onRemove }: Props) {
  const [search, setSearch] = useState("");
  const [draft, setDraft] = useState("");
  const [toRemove, setToRemove] = useState<string | null>(null);

  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase();
    if (!needle) {
      return servers;
    }
    return servers.filter((server) => server.toLowerCase().includes(needle));
  }, [servers, search]);

  const canAdd = Boolean(draft.trim() && !busy);

  const add = () => {
    if (!canAdd) {
      return;
    }
    onAdd(draft.trim());
    setDraft("");
  };

  return (
    <div className="space-y-3">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div className="flex items-center gap-2">
          <Input
            type="search"
            placeholder="Search servers…"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
            className="md:w-56"
            aria-label="Search DNS override servers"
          />
          {search ? (
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setSearch("")}
              aria-label="Clear search"
            >
              <X className="size-4" aria-hidden />
            </Button>
          ) : null}
        </div>
      </div>

      <div className="flex flex-col gap-2 rounded-xl border p-4 sm:flex-row sm:items-end">
        <div className="flex-1 space-y-1.5">
          <Label htmlFor="dns-server">Override server</Label>
          <Input
            id="dns-server"
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                add();
              }
            }}
            placeholder="8.8.8.8 or 1.1.1.1:53"
          />
        </div>
        <Button type="button" onClick={add} disabled={!canAdd}>
          <Plus className="size-4" aria-hidden />
          Add server
        </Button>
      </div>

      {visible.length === 0 ? (
        <div className="rounded-xl border py-10">
          <EmptyState
            message={
              servers.length === 0
                ? "No override servers configured."
                : "No servers match your search."
            }
          />
        </div>
      ) : (
        <ul className="space-y-2">
          {visible.map((server) => (
            <li
              key={server}
              className="flex flex-wrap items-center justify-between gap-3 rounded-md border px-4 py-3"
            >
              <span className="min-w-0 truncate font-mono text-sm">{server}</span>
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => setToRemove(server)}
                aria-label={`Remove ${server}`}
              >
                <Trash2 className="size-4" aria-hidden />
                Remove
              </Button>
            </li>
          ))}
        </ul>
      )}

      <ConfirmDialog
        open={toRemove !== null}
        title={`Remove \u201c${toRemove ?? "server"}\u201d?`}
        description="This override server will be removed from the resolver configuration. Queries fall back to the remaining upstream servers."
        confirmLabel="Remove"
        busy={busy}
        onConfirm={() => {
          if (toRemove) {
            onRemove(toRemove);
          }
          setToRemove(null);
        }}
        onCancel={() => setToRemove(null)}
      />
    </div>
  );
}
