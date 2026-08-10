"use client";

import { KeyRound, Loader2 } from "lucide-react";
import { useState, type FormEvent } from "react";

import { useAuth } from "@/components/auth/auth-boundary";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Logo } from "@/components/ui/logo";

/**
 * Sign-in form. Exchanges an operator API key (AUTH_ADMIN_API_KEY or
 * AUTH_READONLY_API_KEY, configured on the backend) for a short-lived,
 * revocable browser session. The key is sent to the backend once and is never
 * stored or embedded in the bundle.
 */
export function LoginForm() {
  const { login } = useAuth();
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!apiKey.trim() || busy) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await login(apiKey.trim());
      // AuthBoundary observes the new authenticated state and routes onward.
    } catch (err) {
      setError(err instanceof Error ? err.message : "Sign-in failed");
      setBusy(false);
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center gap-3 text-center">
        <Logo withText responsive ariaHiddenText={false} />
        <div className="space-y-1">
          <CardTitle className="text-lg">Sign in</CardTitle>
          <CardDescription>
            Enter an operator API key to open a scoped browser session.
          </CardDescription>
        </div>
      </CardHeader>
      <form onSubmit={onSubmit}>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="api-key">API key</Label>
            <div className="relative">
              <KeyRound
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                id="api-key"
                name="api-key"
                type="password"
                autoComplete="off"
                autoFocus
                placeholder="AUTH_ADMIN_API_KEY or AUTH_READONLY_API_KEY"
                value={apiKey}
                onChange={(event) => setApiKey(event.target.value)}
                className="pl-9"
              />
            </div>
          </div>
          {error ? (
            <p className="text-sm text-destructive" role="alert">
              {error}
            </p>
          ) : null}
          <Button type="submit" className="w-full" disabled={busy || !apiKey.trim()}>
            {busy ? (
              <>
                <Loader2 className="size-4 animate-spin" aria-hidden />
                Signing in…
              </>
            ) : (
              "Sign in"
            )}
          </Button>
        </CardContent>
      </form>
      <CardFooter>
        <p className="w-full text-center text-xs text-muted-foreground">
          Read-only keys can view router state; the admin key also enables
          management actions.
        </p>
      </CardFooter>
    </Card>
  );
}