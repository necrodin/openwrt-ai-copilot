"use client";

import { PackagePlus, Search } from "lucide-react";
import { useState } from "react";

import {
  searchRepository,
  type PackageSearchResponse,
  type PackageSearchResult,
} from "@/lib/router-management";
import type { PackageActionKind } from "@/hooks/use-packages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { EmptyState, Widget, WidgetError } from "@/components/dashboard/widget";

type Props = {
  busy: boolean;
  onAction: (action: PackageActionKind, name: string) => Promise<void>;
};

export function PackagesSearch({ busy, onAction }: Props) {
  const [query, setQuery] = useState("");
  const [submitted, setSubmitted] = useState("");
  const [searching, setSearching] = useState(false);
  const [response, setResponse] = useState<PackageSearchResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<PackageSearchResult | null>(null);

  const runSearch = async (term: string) => {
    const needle = term.trim();
    if (needle === "") {
      return;
    }
    setSearching(true);
    setError(null);
    setResponse(null);
    setSubmitted(needle);
    try {
      const data = await searchRepository(needle);
      setResponse(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setSearching(false);
    }
  };

  const body = (() => {
    if (submitted === "") {
      return (
        <EmptyState message="Search the repository to find packages that can be installed on the router." />
      );
    }
    if (searching) {
      return <EmptyState message={`Searching the repository for “${submitted}”…`} />;
    }
    if (error) {
      return <WidgetError message={error} />;
    }
    if (!response) {
      return <EmptyState message="No results yet." />;
    }
    if (response.results.length === 0) {
      return <EmptyState message={`No packages match “${response.query}” in the repository.`} />;
    }
    return (
      <div className="overflow-x-auto rounded-md border">
        <table className="w-full min-w-[520px] text-sm">
          <thead>
            <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
              <th className="px-3 py-2 font-medium">Package</th>
              <th className="px-3 py-2 font-medium">Version</th>
              <th className="px-3 py-2 font-medium">Description</th>
              <th className="px-3 py-2 text-right font-medium">Action</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {response.results.map((pkg) => (
              <tr key={pkg.name} className="hover:bg-muted/40">
                <td className="px-3 py-2 font-medium">{pkg.name}</td>
                <td className="px-3 py-2 font-mono text-xs text-muted-foreground">{pkg.version || "—"}</td>
                <td className="max-w-md truncate px-3 py-2 text-xs text-muted-foreground">
                  {pkg.description || "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={busy}
                    onClick={() => setPending(pkg)}
                  >
                    <PackagePlus aria-hidden />
                    Install
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  })();

  return (
    <Widget
      title="Repository Search"
      icon={Search}
      subtitle="Find and install packages available from the configured feeds."
    >
      <div className="flex items-center gap-2">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                void runSearch(query);
              }
            }}
            placeholder="Search the package repository…"
            className="pl-9"
            aria-label="Search the package repository"
          />
        </div>
        <Button variant="outline" onClick={() => void runSearch(query)} disabled={searching}>
          {searching ? "Searching…" : "Search"}
        </Button>
      </div>
      {body}
      <ConfirmDialog
        open={pending !== null}
        title={pending ? `Install ${pending.name}?` : ""}
        description={
          pending
            ? `${pending.name} (${pending.version || "latest"}) will be downloaded from the configured feeds and installed on the router.`
            : ""
        }
        confirmLabel="Install"
        tone="default"
        busy={busy}
        onConfirm={async () => {
          if (!pending) return;
          await onAction("install", pending.name);
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      />
    </Widget>
  );
}