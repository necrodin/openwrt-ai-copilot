"use client";

import { Package, RefreshCw, Search } from "lucide-react";
import { useMemo, useState } from "react";

import { usePackages } from "@/hooks/use-packages";
import { Skeleton } from "@/components/ui/skeleton";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { EmptyState, Widget, WidgetError } from "@/components/dashboard/widget";

function managerLabel(manager: string): string {
  if (manager === "apk") return "apk";
  if (manager === "opkg") return "opkg";
  return "package manager";
}

/**
 * Installed Packages (real). Detects apk/opkg on the router, lists installed
 * packages with versions, marks available upgrades, and supports search plus
 * a refresh that busts the backend TTL cache. Loading/empty/error states are
 * handled explicitly.
 */
export function PackagesPanel() {
  const { inventory, loading, error, refresh } = usePackages();
  const [query, setQuery] = useState("");
  const [refreshing, setRefreshing] = useState(false);

  const packages = useMemo(() => inventory?.packages ?? [], [inventory]);
  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (needle === "") {
      return packages;
    }
    return packages.filter(
      (pkg) =>
        pkg.name.toLowerCase().includes(needle) ||
        (pkg.version ?? "").toLowerCase().includes(needle),
    );
  }, [packages, query]);

  const handleRefresh = async () => {
    setRefreshing(true);
    try {
      await refresh();
    } finally {
      setRefreshing(false);
    }
  };

  const body = (() => {
    if (loading && inventory === null) {
      return <Skeleton className="h-24 w-full" />;
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
            onChange={(event) => setQuery(event.target.value)}
            placeholder={`Search ${packages.length} packages…`}
            className="pl-9"
            aria-label="Search packages"
          />
        </div>
        <div className="overflow-x-auto rounded-md border">
          <table className="w-full min-w-[480px] text-sm">
            <thead>
              <tr className="border-b bg-muted/50 text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="px-3 py-2 font-medium">Package</th>
                <th className="px-3 py-2 font-medium">Version</th>
                <th className="px-3 py-2 font-medium">Upgrade</th>
              </tr>
            </thead>
            <tbody className="divide-y">
              {filtered.map((pkg) => (
                <tr key={pkg.name}>
                  <td className="px-3 py-2 font-medium">{pkg.name}</td>
                  <td className="px-3 py-2 font-mono text-xs text-muted-foreground">
                    {pkg.version || "—"}
                  </td>
                  <td className="px-3 py-2">
                    {pkg.upgrade ? (
                      <Badge
                        variant="outline"
                        className="border-emerald-500/40 text-emerald-700 dark:text-emerald-400"
                      >
                        {pkg.upgrade}
                      </Badge>
                    ) : (
                      <span className="text-xs text-muted-foreground">Up to date</span>
                    )}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 ? (
                <tr>
                  <td colSpan={3} className="px-3 py-6 text-center text-sm text-muted-foreground">
                    No packages match “{query}”.
                  </td>
                </tr>
              ) : null}
            </tbody>
          </table>
        </div>
        {filtered.length < packages.length ? (
          <p className="text-xs text-muted-foreground">
            Showing {filtered.length} of {packages.length} packages.
          </p>
        ) : null}
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
      action={
        <Button
          variant="outline"
          size="sm"
          onClick={handleRefresh}
          disabled={refreshing || (loading && inventory === null)}
        >
          <RefreshCw className={refreshing ? "animate-spin" : ""} aria-hidden />
          {refreshing ? "Refreshing…" : "Refresh"}
        </Button>
      }
    >
      {body}
    </Widget>
  );
}