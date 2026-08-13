"use client";

import {
  Loader2,
  Plus,
  Router as RouterIcon,
  ShieldCheck,
  Trash2,
  User,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { useAuth } from "@/components/auth/auth-boundary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { StatusBadge } from "@/components/ui/status-badge";
import { getStoredSession } from "@/lib/auth";
import {
  deleteConnection,
  listConnections,
  type SavedRouter,
} from "@/lib/onboarding";

/**
 * Settings: router management, account/security, and application settings in
 * one place. Router configuration/lifecycle lives here — it is no longer a
 * primary navigation item.
 */
export default function SettingsPage() {
  const auth = useAuth();
  const [routers, setRouters] = useState<SavedRouter[] | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(() => {
    listConnections()
      .then((data) => setRouters(data.routers))
      .catch(() => setRouters([]));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const session = getStoredSession();

  const removeRouter = async (router: SavedRouter) => {
    setBusyId(router.id);
    setError(null);
    try {
      await deleteConnection(router.id);
      reload();
    } catch {
      setError("Could not delete the router connection.");
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="mx-auto w-full max-w-4xl space-y-6 p-4 lg:p-6">
      <header>
        <h1 className="text-2xl font-bold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">
          Router management, account/security, and application preferences.
        </p>
      </header>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Routers</h2>
          <Button asChild size="sm" variant="outline">
            <Link href="/onboarding">
              <Plus className="size-4" aria-hidden />
              Add router
            </Link>
          </Button>
        </div>
        <Card>
          <CardContent className="space-y-2 pt-6">
            {routers === null ? (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <Loader2 className="size-4 animate-spin" aria-hidden />
                Loading routers…
              </p>
            ) : routers.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                No router is connected yet.{" "}
                <Link href="/onboarding" className="text-primary underline underline-offset-4">
                  Connect your router
                </Link>{" "}
                to start managing it.
              </p>
            ) : (
              <ul className="divide-y">
                {routers.map((router) => (
                  <li
                    key={router.id}
                    className="flex flex-wrap items-center justify-between gap-3 py-3"
                  >
                    <div className="flex min-w-0 items-center gap-3">
                      <RouterIcon className="size-5 shrink-0 text-muted-foreground" aria-hidden />
                      <div className="min-w-0 space-y-0.5">
                        <p className="truncate text-sm font-medium">{router.name}</p>
                        <p className="truncate font-mono text-xs text-muted-foreground">
                          {router.host}:{router.port} · {router.username}
                        </p>
                      </div>
                    </div>
                    <div className="flex shrink-0 items-center gap-2">
                      <Button asChild size="sm" variant="outline">
                        <Link href={`/onboarding?reconnect=${router.id}`}>
                          Reconnect
                        </Link>
                      </Button>
                      <Button
                        type="button"
                        size="icon"
                        variant="ghost"
                        aria-label={`Delete router ${router.name}`}
                        title={`Delete ${router.name}`}
                        disabled={busyId === router.id}
                        onClick={() => void removeRouter(router)}
                      >
                        <Trash2 className="size-4" aria-hidden />
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
            {error ? (
              <p className="text-sm text-destructive" role="alert">
                {error}
              </p>
            ) : null}
          </CardContent>
        </Card>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Account / Security</h2>
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <User className="size-4 text-muted-foreground" aria-hidden />
                Current session
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Role</span>
                <StatusBadge
                  label={auth.role === "admin" ? "Admin" : "Read-only"}
                  tone={auth.role === "admin" ? "success" : "info"}
                  dot={false}
                />
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Session token</span>
                <span className="font-medium">{session ? "Active" : "None"}</span>
              </div>
              <p className="text-xs text-muted-foreground">
                {auth.role === "admin"
                  ? "Admin sessions can read router state and perform management actions."
                  : "Read-only sessions can view router state but cannot change it."}
              </p>
              <Button variant="outline" size="sm" onClick={() => void auth.logout()}>
                Sign out
              </Button>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="flex items-center gap-2 text-sm">
                <ShieldCheck className="size-4 text-muted-foreground" aria-hidden />
                Password
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              <p className="text-muted-foreground">
                Passwords are verified with bcrypt and stored only as hashes. No
                change/reset flow is currently exposed by the backend.
              </p>
              <p className="text-xs text-muted-foreground">
                A password reset / change capability is not yet available in this
                release.
              </p>
            </CardContent>
          </Card>
        </div>
      </section>
    </div>
  );
}
