"use client";

import { ArrowDown, ArrowUp, ArrowUpDown, CheckCircle2, Package, PackageX, RefreshCw, RotateCcw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import type { ManagementPackage, PackageInventory } from "@/lib/router-management";
import { formatBytes } from "@/lib/format";
import type { PackageActionKind } from "@/hooks/use-packages";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { EmptyState, Widget, WidgetError } from "@/components/dashboard/widget";

type SortField = "name" | "version";
type SortDir = "asc" | "desc";

type Props = {
  inventory: PackageInventory | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  selected: string | null;
  onSelect: (name: string) => void;
  onAction: (action: PackageActionKind, name: string) => Promise<void>;
};

const PAGE_SIZE = 25;

function managerLabel(manager: string): string {
  if (manager === "apk") return "apk";
  if (manager === "opkg") return "opkg";
  return "package manager";
}

export function PackagesInstalled({
  inventory,
  loading,
  error,
  busy,
  selected,
  onSelect,
  onAction,
}: Props) {
  const [query, setQuery] = useState("");
  const [sortField, setSortField] = useState<SortField>("name");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [page, setPage] = useState(0);
  const [pending, setPending] = useState<
    { action: "upgrade" | "reinstall" | "remove"; pkg: ManagementPackage } | null
  >(null);

  const packages = useMemo(() => inventory?.packages ?? [], [inventory]);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    const base = needle
      ? packages.filter(
          (pkg) =>
            pkg.name.toLowerCase().includes(needle) ||
            (pkg.version ?? "").toLowerCase().includes(needle) ||
            (pkg.architecture ?? "").toLowerCase().includes(needle) ||
            (pkg.description ?? "").toLowerCase().includes(needle),
        )
      : packages;
    const sorted = [...base].sort((a, b) => {
      const left = a[sortField] ?? "";
      const right = b[sortField] ?? "";
      const cmp = String(left).localeCompare(String(right));
      return sortDir === "asc" ? cmp : -cmp;
    });
    return sorted;
  }, [packages, query, sortField, sortDir]);

  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const paged = useMemo(
    () => filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE),
    [filtered, safePage],
  );

  const toggleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDir((dir) => (dir === "asc" ? "desc" : "asc"));
    } else {
      setSortField(field);
      setSortDir("asc");
    }
    setPage(0);
  };

  const confirmPending = async () => {
    if (!pending) return;
    await onAction(pending.action, pending.pkg.name);
    setPending(null);
  };

  const body = (() => {
    if (loading && inventory === null) {
      return <Skeleton className="h-48 w-full" />;
    }
    if (!loading && inventory === null && error !== null) {
      return <WidgetError message={error} />;
    }
    if (packages.length === 0) {
      return <EmptyState message="No installed packages were reported by the router." />;
    }
    return (
      <div className="space-y-3">
        <div className="relative">
          <Search
            className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setPage(0);
            }}
            placeholder={`Search ${packages.length} installed packages…`}
            className="pl-9"
            aria-label="Search installed packages"
          />
        </div>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">
                  <button
                    type="button"
                    onClick={() => toggleSort("name")}
                    className="inline-flex items-center gap-1 hover:text-foreground"
                  >
                    Package
                    {sortField === "name" ? (
                      sortDir === "asc" ? (
                        <ArrowUp className="size-3" />
                      ) : (
                        <ArrowDown className="size-3" />
                      )
                    ) : (
                      <ArrowUpDown className="size-3" />
                    )}
                  </button>
                </th>
                <th className="px-3 py-2 font-medium">
                  <button
                    type="button"
                    onClick={() => toggleSort("version")}
                    className="inline-flex items-center gap-1 hover:text-foreground"
                  >
                    Version
                    {sortField === "version" ? (
                      sortDir === "asc" ? (
                        <ArrowUp className="size-3" />
                      ) : (
                        <ArrowDown className="size-3" />
                      )
                    ) : (
                      <ArrowUpDown className="size-3" />
                    )}
                  </button>
                </th>
                <th className="px-3 py-2 font-medium">Size</th>
                <th className="px-3 py-2 font-medium">Architecture</th>
                <th className="px-3 py-2 font-medium">Upgrade</th>
                <th className="px-3 py-2 text-right font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {paged.map((pkg) => (
                <tr
                  key={pkg.name}
                  className={selected === pkg.name ? "bg-accent/50" : "hover:bg-muted/40"}
                >
                  <td className="px-3 py-2">
                    <button
                      type="button"
                      onClick={() => onSelect(pkg.name)}
                      className="text-left font-medium hover:text-primary hover:underline"
                    >
                      {pkg.name}
                    </button>
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {pkg.version || "—"}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {formatBytes(pkg.size)}
                  </td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">{pkg.architecture || "—"}</td>
                  <td className="px-3 py-2">
                    {pkg.upgrade ? (
                      <Badge
                        variant="outline"
                        className="border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
                      >
                        {pkg.upgrade}
                      </Badge>
                    ) : (
                      <Badge variant="outline">
                        <CheckCircle2 className="text-emerald-500" aria-hidden />
                        Up to date
                      </Badge>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <div className="flex items-center justify-end gap-1.5">
                      {pkg.upgrade ? (
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={busy}
                          onClick={() => setPending({ action: "upgrade", pkg })}
                        >
                          <RefreshCw aria-hidden />
                          Upgrade
                        </Button>
                      ) : null}
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={busy}
                        onClick={() => setPending({ action: "reinstall", pkg })}
                      >
                        <RotateCcw aria-hidden />
                        Reinstall
                      </Button>
                      <Button
                        variant="ghost"
                        size="icon"
                        className="text-muted-foreground hover:text-destructive"
                        disabled={busy}
                        aria-label={`Remove ${pkg.name}`}
                        onClick={() => setPending({ action: "remove", pkg })}
                      >
                        <PackageX aria-hidden />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
              {paged.length === 0 ? (
                <tr>
                  <td colSpan={6} className="px-3 py-6 text-center text-sm text-muted-foreground">
                    No packages match “{query}”.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>
            Showing {paged.length} of {filtered.length} package{paged.length === 1 ? "" : "s"}
            {filtered.length !== packages.length
              ? ` (${packages.length} total, filtered)`
              : ""}
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
            >
              Previous
            </Button>
            <span>
              Page {safePage + 1} of {pageCount}
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage(safePage + 1)}
            >
              Next
            </Button>
          </div>
        </div>
      </div>
    );
  })();

  return (
    <Widget
      title="Installed Packages"
      icon={Package}
      subtitle={
        inventory
          ? `${managerLabel(inventory.manager)} · ${packages.length} installed · ${inventory.upgrades_available} update${inventory.upgrades_available === 1 ? "" : "s"} available`
          : "Package inventory loading…"
      }
    >
      {body}
      <ConfirmDialog
        open={pending !== null}
        title={
          pending
            ? pending.action === "remove"
              ? `Remove ${pending.pkg.name}?`
              : pending.action === "upgrade"
                ? `Upgrade ${pending.pkg.name}?`
                : `Reinstall ${pending.pkg.name}?`
            : ""
        }
        description={
          pending
            ? pending.action === "remove"
              ? `This will uninstall ${pending.pkg.name} (${pending.pkg.version || "unknown version"}) from the router. Packages that depend on it may be affected.`
              : pending.action === "upgrade"
                ? `${pending.pkg.name} will be upgraded to ${pending.pkg.upgrade}.`
                : `${pending.pkg.name} will be reinstalled at its current version.`
            : ""
        }
        confirmLabel="Confirm"
        tone={pending?.action === "remove" ? "destructive" : "default"}
        busy={busy}
        onConfirm={confirmPending}
        onCancel={() => setPending(null)}
      />
    </Widget>
  );
}