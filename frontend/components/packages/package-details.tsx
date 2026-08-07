"use client";

import { ExternalLink, Package, PackageCheck, PackagePlus, PackageX, RotateCcw } from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";

import { fetchPackageDetails, type PackageDetails } from "@/lib/router-management";
import { formatBytes } from "@/lib/format";
import type { PackageActionKind } from "@/hooks/use-packages";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { Widget, WidgetError } from "@/components/dashboard/widget";

type Props = {
  name: string;
  installed: boolean;
  installedVersion: string | null;
  upgrade: string | null;
  busy: boolean;
  onAction: (action: PackageActionKind, name: string) => Promise<void>;
};

type PendingAction = PackageActionKind | null;

function InfoRow({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="grid grid-cols-[160px_1fr] gap-3 py-1.5 text-sm">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className={mono ? "font-mono text-xs leading-6" : ""}>{value}</dd>
    </div>
  );
}

export function PackageDetails({ name, installed, installedVersion, upgrade, busy, onAction }: Props) {
  const [details, setDetails] = useState<PackageDetails | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [pending, setPending] = useState<PendingAction>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setDetails(null);
    fetchPackageDetails(name)
      .then((data) => {
        if (!cancelled) setDetails(data);
      })
      .catch((err: unknown) => {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : String(err));
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [name]);

  const confirmPending = async () => {
    if (!pending) return;
    await onAction(pending, name);
    setPending(null);
  };

  const actions: Array<{ action: PackageActionKind; label: string; icon: typeof PackagePlus; destructive?: boolean }> =
    [];
  if (!installed) {
    actions.push({ action: "install", label: "Install", icon: PackageCheck });
  } else {
    if (upgrade) {
      actions.push({ action: "upgrade", label: `Upgrade to ${upgrade}`, icon: PackageCheck });
    }
    actions.push({ action: "reinstall", label: "Reinstall", icon: RotateCcw });
    actions.push({ action: "remove", label: "Remove", icon: PackageX, destructive: true });
  }

  const body = (() => {
    if (loading) {
      return <Skeleton className="h-32 w-full" />;
    }
    if (error) {
      return <WidgetError message={error} />;
    }
    if (!details) {
      return <WidgetError message="No details were returned for this package." />;
    }
    return (
      <dl className="divide-y">
        <InfoRow label="Name" value={details.name} mono />
        <InfoRow label="Version" value={details.version} mono />
        <InfoRow label="Installed" value={installed ? installedVersion || "yes" : "No"} />
        {upgrade ? (
          <InfoRow
            label="Upgrade available"
            value={<Badge variant="outline" className="border-emerald-500/40 text-emerald-700 dark:text-emerald-400">{upgrade}</Badge>}
          />
        ) : null}
        <InfoRow label="Architecture" value={details.architecture || "—"} mono />
        <InfoRow label="Section" value={details.section || "—"} />
        <InfoRow label="License" value={details.license || "—"} />
        <InfoRow
          label="Installed size"
          value={details.installed_size != null ? formatBytes(details.installed_size) : "—"}
        />
        <InfoRow
          label="Download size"
          value={details.download_size != null ? formatBytes(details.download_size) : "—"}
        />
        <InfoRow
          label="Maintainer"
          value={
            details.maintainer ? (
              <a
                href={`mailto:${details.maintainer}`}
                className="text-primary hover:underline"
              >
                {details.maintainer}
              </a>
            ) : (
              "—"
            )
          }
        />
        <InfoRow
          label="Homepage"
          value={
            details.homepage ? (
              <a
                href={details.homepage}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 text-primary hover:underline"
              >
                <ExternalLink className="size-3" aria-hidden />
                {details.homepage}
              </a>
            ) : (
              "—"
            )
          }
        />
        <InfoRow
          label="Depends"
          value={
            details.depends.length > 0 ? (
              <div className="flex flex-wrap gap-1 pt-1">
                {details.depends.map((dep) => (
                  <Badge key={dep} variant="secondary">
                    {dep}
                  </Badge>
                ))}
              </div>
            ) : (
              "—"
            )
          }
        />
        <InfoRow label="Description" value={details.description || "—"} />
      </dl>
    );
  })();

  return (
    <Widget
      title={`Package ${name}`}
      icon={Package}
      subtitle={
        installed
          ? upgrade
            ? "Installed · an upgrade is available"
            : "Installed · up to date"
          : "Not installed · available from the repository"
      }
      action={
        actions.length > 0 ? (
          <div className="flex items-center gap-2">
            {actions.map((a) => (
              <Button
                key={a.action}
                variant={a.destructive ? "destructive" : "outline"}
                size="sm"
                disabled={busy}
                onClick={() => setPending(a.action)}
              >
                <a.icon aria-hidden />
                {a.label}
              </Button>
            ))}
          </div>
        ) : null
      }
    >
      {body}
      <ConfirmDialog
        open={pending !== null}
        title={
          pending === "install"
            ? `Install ${name}?`
            : pending === "remove"
              ? `Remove ${name}?`
              : pending === "upgrade"
                ? `Upgrade ${name}?`
                : `Reinstall ${name}?`
        }
        description={
          pending === "remove"
            ? `This will uninstall ${name} from the router. Packages that depend on it may be affected.`
            : pending === "install"
              ? `${name} will be downloaded from the configured feeds and installed.`
              : pending === "upgrade"
                ? `${name} will be upgraded to the newest available version.`
                : `${name} will be removed and reinstalled at the current version.`
        }
        confirmLabel="Confirm"
        tone={pending === "remove" ? "destructive" : "default"}
        busy={busy}
        onConfirm={confirmPending}
        onCancel={() => setPending(null)}
      />
    </Widget>
  );
}