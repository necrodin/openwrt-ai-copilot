import { HealthStatus } from "@/components/health-status";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export default function Home() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center gap-10 p-8">
      <div className="space-y-3 text-center">
        <h1 className="text-4xl font-bold tracking-tight">OpenWrt AI Copilot</h1>
        <p className="text-muted-foreground">
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

      <Button asChild>
        <a href="/dashboard">Open live dashboard</a>
      </Button>

      <Button asChild variant="outline">
        <a
          href="https://openwrt.org"
          target="_blank"
          rel="noreferrer"
        >
          About OpenWrt
        </a>
      </Button>
    </main>
  );
}
