"use client";

import { Boxes, HardDriveDownload, PackageCheck, RefreshCw } from "lucide-react";

import type { PackageFeeds, PackageInventory, PackageManager } from "@/lib/router-management";
import { formatEpoch } from "@/lib/format";
import { Card, CardContent } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";

type Props = {
  inventory: PackageInventory | null;
  feeds: PackageFeeds | null;
};

function formatEpochLocal(epoch: number | null): string {
  return formatEpoch(epoch);
}

function managerLabel(manager: PackageManager): string {
  if (manager === "apk") return "apk";
  if (manager === "opkg") return "opkg";
  return "unknown";
}

export function PackagesOverview({ inventory, feeds }: Props) {
  const installed = inventory?.count ?? 0;
  const upgradable = inventory?.upgrades_available ?? 0;
  const feedCount = feeds?.count ?? 0;

  const items = [
    {
      label: "Installed packages",
      value: String(installed),
      icon: PackageCheck,
      sub: inventory ? `${managerLabel(inventory.manager)} package database` : null,
    },
    {
      label: "Upgradable",
      value: String(upgradable),
      icon: RefreshCw,
      sub:
        upgradable > 0
          ? "updates available"
          : inventory
            ? "all up to date"
            : null,
    },
    {
      label: "Configured feeds",
      value: String(feedCount),
      icon: Boxes,
      sub: feeds ? `last updated ${formatEpochLocal(feeds.last_update)}` : null,
    },
    {
      label: "Package database",
      value: inventory ? managerLabel(inventory.manager).toUpperCase() : "—",
      icon: HardDriveDownload,
      sub: inventory ? "live, pulled from the router" : "waiting for data",
    },
  ];

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {items.map((item) => {
        const Icon = item.icon;
        return (
          <Card key={item.label}>
            <CardContent className="space-y-2">
              <div className="flex items-center gap-2">
                <Icon className="size-4 text-muted-foreground" aria-hidden />
                <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                  {item.label}
                </p>
              </div>
              <p className="text-2xl font-semibold tabular-nums">{item.value}</p>
              {item.sub ? (
                <p className="text-xs text-muted-foreground">{item.sub}</p>
              ) : null}
            </CardContent>
          </Card>
        );
      })}
      <div className="sm:col-span-2 xl:col-span-4">
        <StatusBadge
          tone={inventory && upgradable > 0 ? "warning" : "success"}
          label={
            inventory
              ? upgradable > 0
                ? `${upgradable} package${upgradable === 1 ? "" : "s"} can be upgraded`
                : "All installed packages are up to date"
              : "Package data loading…"
          }
        />
      </div>
    </div>
  );
}