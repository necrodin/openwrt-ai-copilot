"use client";

import { Bot, Sparkles, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { StatusBadge } from "@/components/ui/status-badge";
import { ChartPlaceholder } from "@/components/dashboard/chart-placeholder";

/**
 * Right-hand AI Copilot panel. Presentational placeholder only — no backend
 * wiring is performed in this sprint.
 */
export function AiCopilotPanel() {
  const [open, setOpen] = useState(true);

  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="hidden shrink-0 items-center justify-center border-l bg-card/40 text-muted-foreground transition-colors hover:text-foreground lg:flex lg:w-10"
        aria-label="Open AI copilot panel"
      >
        <Bot className="size-4" aria-hidden />
      </button>
    );
  }

  return (
    <aside className="hidden shrink-0 border-l bg-card/40 lg:flex lg:w-80 lg:flex-col">
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="size-4 text-primary" aria-hidden />
          <h2 className="text-sm font-semibold">AI Copilot</h2>
        </div>
        <Button
          variant="ghost"
          size="icon"
          onClick={() => setOpen(false)}
          aria-label="Hide AI copilot panel"
        >
          <X className="size-4" aria-hidden />
        </Button>
      </div>

      <div className="flex-1 space-y-4 overflow-y-auto p-4">
        <StatusBadge label="Coming in a future sprint" tone="info" />
        <p className="text-sm text-muted-foreground">
          The copilot panel will surface natural-language diagnostics, recommended
          actions, and guided remediation alongside the live dashboard.
        </p>
        <ChartPlaceholder label="Projected throughput — illustrative" />
        <div className="flex items-start gap-2 rounded-md border px-3 py-2 text-sm">
          <Sparkles className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
          <span className="text-muted-foreground">
            Nothing here yet — this panel is a placeholder.
          </span>
        </div>
      </div>
    </aside>
  );
}
