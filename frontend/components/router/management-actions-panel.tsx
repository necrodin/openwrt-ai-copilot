"use client";

import {
  ArchiveRestore,
  DatabaseBackup,
  FileArchive,
  FolderSync,
  Power,
  RotateCw,
  Server,
  WifiOff,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Widget } from "@/components/dashboard/widget";

type Action = {
  id: string;
  label: string;
  description: string;
  icon: LucideIcon;
  variant: "default" | "destructive" | "outline" | "secondary";
};

type Group = {
  title: string;
  actionLabel: string;
  actions: Action[];
};

const GROUPS: Group[] = [
  {
    title: "System",
    actionLabel: "Device power",
    actions: [
      { id: "reboot", label: "Reboot", description: "Reboot the router", icon: RotateCw, variant: "default" },
      { id: "shutdown", label: "Shutdown", description: "Power the router down", icon: Power, variant: "destructive" },
    ],
  },
  {
    title: "Network",
    actionLabel: "Network services",
    actions: [
      { id: "restart-network", label: "Restart Network", description: "Restart network interfaces", icon: Server, variant: "default" },
      { id: "restart-wifi", label: "Restart WiFi", description: "Restart wireless radios", icon: WifiOff, variant: "secondary" },
      { id: "restart-firewall", label: "Restart Firewall", description: "Reload firewall rules", icon: FolderSync, variant: "default" },
    ],
  },
  {
    title: "Data",
    actionLabel: "Device data",
    actions: [
      { id: "backup", label: "Backup", description: "Export configuration backup", icon: DatabaseBackup, variant: "default" },
      { id: "restore", label: "Restore", description: "Import configuration backup", icon: ArchiveRestore, variant: "outline" },
      { id: "diagnostic-bundle", label: "Diagnostic Bundle", description: "Generate troubleshooting archive", icon: FileArchive, variant: "secondary" },
    ],
  },
];

/**
 * Management action surface for physical OpenWrt operations. No management
 * endpoints exist on the backend yet, so every action is rendered as a real,
 * disabled control with an explicit "Coming in next sprint" note — never a
 * fake clickable placeholder.
 */
export function ManagementActionsPanel() {
  let total = 0;
  for (const group of GROUPS) {
    total += group.actions.length;
  }

  return (
    <Widget
      title="Management Actions"
      icon={DatabaseBackup}
      subtitle={`${total} actions prepared`}
    >
      <div className="space-y-5">
        <p className="rounded-md border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-sm text-amber-700 dark:text-amber-400">
          Destructive operation endpoints are not exposed by the backend yet.
          The controls below are wired and disabled; return to this page next
          sprint to trigger them live. No action has been executed.
        </p>

        {GROUPS.map((group) => (
          <div key={group.title} className="space-y-2">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold">{group.title}</h3>
              <span className="text-xs text-muted-foreground">{group.actionLabel}</span>
            </div>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
              {group.actions.map((action) => {
                const Icon = action.icon;
                return (
                  <div
                    key={action.id}
                    className="flex flex-col gap-3 rounded-md border p-3"
                  >
                    <div className="flex items-start gap-3">
                      <span className="flex size-9 shrink-0 items-center justify-center rounded-md border bg-muted">
                        <Icon className="size-4 text-muted-foreground" aria-hidden />
                      </span>
                      <div className="min-w-0 space-y-0.5">
                        <p className="truncate text-sm font-medium">{action.label}</p>
                        <p className="text-xs text-muted-foreground">{action.description}</p>
                      </div>
                    </div>
                    <div className="mt-auto flex items-center justify-between gap-2">
                      <Badge variant="secondary">Coming in next sprint</Badge>
                      <Button
                        variant={action.variant}
                        size="sm"
                        disabled
                        title="Available once the management API ships"
                      >
                        {action.label}
                      </Button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </Widget>
  );
}