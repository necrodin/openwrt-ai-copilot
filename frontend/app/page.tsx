"use client";

import { Loader2, Router } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Footer } from "@/components/layout/footer";
import { HealthStatus } from "@/components/health-status";
import { Logo } from "@/components/ui/logo";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { listConnections, type SavedRouter } from "@/lib/onboarding";

export default function Home() {
  const router = useRouter();
  const [routers, setRouters] = useState<SavedRouter[] | null>(null);

  useEffect(() => {
    let cancelled = false;
    listConnections()
      .then((data) => {
        if (cancelled) {
          return;
        }
        setRouters(data.routers);
        if (data.routers.length === 0) {
          router.replace("/onboarding");
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRouters([]);
          router.replace("/onboarding");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  const configured = (routers?.length ?? 0) > 0;
  const activeRouter = routers?.[0] ?? null;

  if (routers === null) {
    return (
      <main className="flex min-h-screen flex-col items-center justify-center gap-4 p-8">
        <Loader2 className="size-6 animate-spin text-muted-foreground" aria-hidden />
        <p className="text-sm text-muted-foreground">Checking router setup…</p>
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col">
      <div className="flex flex-1 flex-col items-center justify-center gap-10 p-8">
        <div className="space-y-4 text-center">
          <Logo className="justify-center" withText responsive />
          <h1 className="sr-only">OpenWrt AI Copilot</h1>
          <p className="mx-auto max-w-xl text-muted-foreground">
            Provider-independent AI copilot for OpenWrt networks.
          </p>
        </div>

      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-base">System status</CardTitle>
          <CardDescription>
            Connectivity between the web UI and the FastAPI backend.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex items-center justify-between">
          <span className="text-sm text-muted-foreground">Backend API</span>
          <HealthStatus />
        </CardContent>
      </Card>

      {routers === null ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="size-4 animate-spin" aria-hidden />
          Checking router setup…
        </div>
      ) : configured ? (
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Router className="size-4" aria-hidden />
              {activeRouter?.name ?? "Your router"}
            </CardTitle>
            <CardDescription>
              {activeRouter?.host}:{activeRouter?.port} · live data via SSH
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild variant="outline" size="sm">
              <a href="/onboarding">Manage connection</a>
            </Button>
          </CardContent>
        </Card>
      ) : (
        <Card className="w-full max-w-sm">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Router className="size-4" aria-hidden />
              No router connected yet
            </CardTitle>
            <CardDescription>
              Point the copilot at your OpenWrt device to see live data. Until
              then the dashboard and chat stay empty — no demo data.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <Button asChild>
              <a href="/onboarding">Connect your router</a>
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="flex flex-wrap items-center justify-center gap-3">
        <Button asChild disabled={!configured}>
          <a href="/chat">Open AI chat</a>
        </Button>
        <Button asChild variant="outline" disabled={!configured}>
          <a href="/dashboard">Open live dashboard</a>
        </Button>
      </div>

      <Button asChild variant="ghost">
        <a
          href="https://openwrt.org"
          target="_blank"
          rel="noreferrer"
        >
          About OpenWrt
        </a>
      </Button>
      </div>
      <Footer />
    </main>
  );
}
