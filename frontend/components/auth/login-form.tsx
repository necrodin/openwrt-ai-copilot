"use client";

import { Loader2, Lock, User } from "lucide-react";
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
 * Sign-in form. Browser users authenticate with a username and password
 * configured server-side (AUTH_ADMIN_USERNAME/PASSWORD for full access and
 * AUTH_READONLY_USERNAME/PASSWORD for read-only access). The backend exchanges
 * the credentials for a short-lived, revocable browser session; credentials
 * are never stored in the browser or returned to it.
 */
export function LoginForm() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [invalid, setInvalid] = useState(false);

  async function onSubmit(event: FormEvent) {
    event.preventDefault();
    if (!username.trim() || !password || busy) {
      return;
    }
    setBusy(true);
    setInvalid(false);
    try {
      await login(username.trim(), password);
      // AuthBoundary observes the new authenticated state and routes onward.
    } catch (err) {
      setInvalid(true);
      setBusy(false);
      void err;
    }
  }

  return (
    <Card className="w-full max-w-sm">
      <CardHeader className="items-center gap-3 text-center">
        <Logo withText responsive ariaHiddenText={false} />
        <div className="space-y-1">
          <CardTitle className="text-lg">Sign in</CardTitle>
          <CardDescription>
            Sign in to open a scoped browser session.
          </CardDescription>
        </div>
      </CardHeader>
      <form onSubmit={onSubmit} noValidate>
        <CardContent className="space-y-3">
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
            <div className="relative">
              <User
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                id="username"
                name="username"
                type="text"
                autoComplete="username"
                autoFocus
                value={username}
                onChange={(event) => {
                  setUsername(event.target.value);
                  setInvalid(false);
                }}
                className="pl-9"
              />
            </div>
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <div className="relative">
              <Lock
                className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground"
                aria-hidden
              />
              <Input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => {
                  setPassword(event.target.value);
                  setInvalid(false);
                }}
                className="pl-9"
              />
            </div>
          </div>
          {invalid ? (
            <p className="text-sm text-destructive" role="alert">
              Invalid username or password.
            </p>
          ) : null}
          <Button
            type="submit"
            className="w-full"
            disabled={busy || !username.trim() || !password}
          >
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
          Read-only accounts can view router state; the admin account also
          enables management actions.
        </p>
      </CardFooter>
    </Card>
  );
}