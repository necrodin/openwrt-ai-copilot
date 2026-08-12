"use client";

import { Check, Pencil, Tag, X } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Props = {
  label: string | null;
  canEdit: boolean;
  onSave: (label: string) => Promise<void>;
  onClear: () => Promise<void>;
};

/**
 * Inline editor for a client's persistent label.
 *
 * Shows the label (or "—") with an edit affordance for write-enabled
 * operators. Editing allows entering a label, saving it, cancelling, or
 * clearing (deleting) the stored label. Purely optional metadata: clients
 * without a label are untouched.
 */
export function ClientLabelEditor({ label, canEdit, onSave, onClear }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(label ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startEdit = () => {
    setValue(label ?? "");
    setError(null);
    setEditing(true);
  };

  const cancel = () => {
    setEditing(false);
    setError(null);
  };

  const save = async () => {
    const trimmed = value.trim();
    if (!trimmed) {
      setError("Label must not be empty.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await onSave(trimmed);
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const clear = async () => {
    setBusy(true);
    setError(null);
    try {
      await onClear();
      setValue("");
      setEditing(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="rounded-lg border bg-muted/30 px-3 py-2">
      <div className="flex items-center gap-2">
        <span className="flex size-7 shrink-0 items-center justify-center rounded-md border bg-background">
          <Tag className="size-3.5 text-muted-foreground" aria-hidden />
        </span>
        <span className="min-w-0 flex-1 truncate text-sm font-medium">
          {editing ? (
            <Input
              value={value}
              onChange={(event) => setValue(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter") {
                  void save();
                } else if (event.key === "Escape") {
                  cancel();
                }
              }}
              placeholder="Enter a label…"
              maxLength={255}
              aria-label="Client label"
              className="h-7"
              autoFocus
            />
          ) : (
            <span className={label ? "" : "text-muted-foreground"}>
              {label || "No label"}
            </span>
          )}
        </span>
        {canEdit && !editing ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="size-7"
            onClick={startEdit}
            aria-label="Edit label"
          >
            <Pencil className="size-3.5" aria-hidden />
          </Button>
        ) : null}
        {editing ? (
          <span className="flex shrink-0 items-center gap-1">
            {label ? (
              <Button
                type="button"
                variant="ghost"
                size="sm"
                className="h-7 px-2 text-xs"
                onClick={clear}
                disabled={busy}
              >
                Clear
              </Button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="size-7"
              onClick={cancel}
              disabled={busy}
              aria-label="Cancel"
            >
              <X className="size-3.5" aria-hidden />
            </Button>
            <Button
              type="button"
              variant="default"
              size="icon"
              className="size-7"
              onClick={save}
              disabled={busy}
              aria-label="Save label"
            >
              <Check className="size-3.5" aria-hidden />
            </Button>
          </span>
        ) : null}
      </div>
      {error ? <p className="pt-1.5 text-xs text-destructive">{error}</p> : null}
    </div>
  );
}
