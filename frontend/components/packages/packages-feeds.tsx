"use client";

import { Boxes, RefreshCw } from "lucide-react";

import type { PackageFeeds } from "@/lib/router-management";
import { formatEpoch } from "@/lib/format";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { ConfirmDialog } from "@/components/router/confirm-dialog";
import { EmptyState, Widget, WidgetError } from "@/components/dashboard/widget";
import { useState } from "react";

type Props = {
  feeds: PackageFeeds | null;
  loading: boolean;
  error: string | null;
  busy: boolean;
  onUpdate: () => Promise<void>;
};

export function PackagesFeeds({ feeds, loading, error, busy, onUpdate }: Props) {
  const [confirming, setConfirming] = useState(false);

  const body = (() => {
    if (loading && feeds === null) {
      return <Skeleton className="h-24 w-full" />;
    }
    if (!loading && feeds === null && error !== null) {
      return <WidgetError message={error} />;
    }
    if (!feeds || feeds.feeds.length === 0) {
      return <EmptyState message="No package feeds were reported by the router." />;
    }
    return (
      <div className="space-y-2">
        {feeds.feeds.map((feed) => (
          <div
            key={`${feed.type}-${feed.name}`}
            className="flex flex-wrap items-center justify-between gap-2 rounded-md border px-3 py-2 text-sm"
          >
            <div className="min-w-0 space-y-0.5">
              <p className="font-medium">
                {feed.name}
                <span className="ml-2 rounded bg-muted px-1.5 py-0.5 text-xs uppercase tracking-wide text-muted-foreground">
                  {feed.type}
                </span>
              </p>
              <p className="truncate font-mono text-xs text-muted-foreground">{feed.url}</p>
            </div>
            <p className="text-xs text-muted-foreground">{feed.source}</p>
          </div>
        ))}
      </div>
    );
  })();

  return (
    <Widget
      title="Package Feeds"
      icon={Boxes}
      subtitle={
        feeds
          ? `${feeds.count} configured feed${feeds.count === 1 ? "" : "s"} · last updated ${formatEpoch(feeds.last_update)}`
          : "Feed configuration loading…"
      }
      action={
        <Button
          variant="outline"
          size="sm"
          disabled={busy}
          onClick={() => setConfirming(true)}
        >
          <RefreshCw aria-hidden />
          Update feeds
        </Button>
      }
    >
      {body}
      <ConfirmDialog
        open={confirming}
        title="Update package feeds?"
        description="This refreshes the package lists from all configured feeds on the router, which is recommended before searching for or installing packages."
        confirmLabel="Update"
        tone="default"
        busy={busy}
        onConfirm={async () => {
          await onUpdate();
          setConfirming(false);
        }}
        onCancel={() => setConfirming(false)}
      />
    </Widget>
  );
}