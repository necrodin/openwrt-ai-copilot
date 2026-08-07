"use client";

import { useEffect, useState } from "react";
import { Save } from "lucide-react";

import type { SystemInfo } from "@/lib/router-management";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Props = {
  system: SystemInfo;
  busy?: boolean;
  onSave: (config: {
    hostname: string;
    timezone: string;
    language: string;
    notes: string;
  }) => Promise<void>;
};

export function SystemConfig({ system, busy = false, onSave }: Props) {
  const [hostname, setHostname] = useState(system.hostname);
  const [timezone, setTimezone] = useState(system.timezone);
  const [language, setLanguage] = useState(system.language);
  const [notes, setNotes] = useState(system.notes);

  useEffect(() => {
    setHostname(system.hostname);
    setTimezone(system.timezone);
    setLanguage(system.language);
    setNotes(system.notes);
  }, [system]);

  const dirty =
    hostname !== system.hostname ||
    timezone !== system.timezone ||
    language !== system.language ||
    notes !== system.notes;

  const canSave = hostname.trim().length > 0 && timezone.trim().length > 0;

  return (
    <Card>
      <CardContent className="space-y-4">
        <div>
          <h3 className="text-sm font-semibold">System configuration</h3>
          <p className="text-xs text-muted-foreground">
            These settings are saved to the router with <code>uci commit</code>.
          </p>
        </div>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="system-hostname">Hostname</Label>
            <Input
              id="system-hostname"
              value={hostname}
              onChange={(event) => setHostname(event.target.value)}
              placeholder="router"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="system-timezone">
              Timezone {system.zonename ? `(${system.zonename})` : ""}
            </Label>
            <Input
              id="system-timezone"
              value={timezone}
              onChange={(event) => setTimezone(event.target.value)}
              placeholder="UTC"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="system-language">Language</Label>
            <Input
              id="system-language"
              value={language}
              onChange={(event) => setLanguage(event.target.value)}
              placeholder="en"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        </div>

        <div className="space-y-1.5">
          <Label htmlFor="system-notes">Notes / Description</Label>
          <textarea
            id="system-notes"
            value={notes}
            onChange={(event) => setNotes(event.target.value)}
            rows={3}
            placeholder="Optional description of this device…"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring"
          />
        </div>

        <div className="flex items-center gap-3">
          <Button
            onClick={() =>
              void onSave({ hostname: hostname.trim(), timezone: timezone.trim(), language: language.trim(), notes })
            }
            disabled={busy || !canSave || !dirty}
          >
            <Save className="size-4" aria-hidden />
            Save configuration
          </Button>
          {!dirty ? (
            <span className="text-xs text-muted-foreground">No unsaved changes.</span>
          ) : null}
        </div>
      </CardContent>
    </Card>
  );
}