import { Hammer, type LucideIcon } from "lucide-react";
import Link from "next/link";

import { Button } from "@/components/ui/button";

type ComingSoonProps = {
  title: string;
  description: string;
  icon: LucideIcon;
};

/**
 * Placeholder screen for console pages that are not implemented yet. Only the
 * Dashboard page is functional in this sprint.
 */
export function ComingSoon({ title, description, icon: Icon }: ComingSoonProps) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center gap-5 p-6 text-center">
      <span className="flex size-14 items-center justify-center rounded-2xl border bg-muted">
        <Icon className="size-7 text-muted-foreground" aria-hidden />
      </span>
      <div className="space-y-1.5">
        <h1 className="flex items-center justify-center gap-2 text-2xl font-bold tracking-tight">
          <Hammer className="size-5 text-muted-foreground" aria-hidden />
          {title}
        </h1>
        <p className="mx-auto max-w-md text-sm text-muted-foreground">{description}</p>
      </div>
      <Button asChild variant="outline">
        <Link href="/dashboard">Back to Dashboard</Link>
      </Button>
    </div>
  );
}
