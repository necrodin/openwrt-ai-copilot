"use client";

import {
  CheckCircle2,
  Loader2,
  Wifi,
  XCircle,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

import { Footer } from "@/components/layout/footer";
import { Logo } from "@/components/ui/logo";
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
import { Skeleton } from "@/components/ui/skeleton";
import {
  detectDevice,
  listConnections,
  saveRouter,
  type DeviceInfo,
  type NetworkInterfaceSummary,
  type RouterCredentials,
  type SavedRouter,
  type WifiRadioSummary,
} from "@/lib/onboarding";
import { cn } from "@/lib/utils";

const DEFAULT_CREDENTIALS: RouterCredentials = {
  host: "192.168.1.1",
  port: 22,
  username: "root",
  authType: "password",
  password: "",
  privateKey: "",
};

type View = "welcome" | "form" | "connected";

function validateCredentials(credentials: RouterCredentials): string | null {
  if (!credentials.host.trim()) {
    return "Host address is required.";
  }
  if (credentials.port < 1 || credentials.port > 65535) {
    return "Port must be between 1 and 65535.";
  }
  if (!credentials.username.trim()) {
    return "SSH username is required.";
  }
  if (
    credentials.authType === "password" &&
    !credentials.password.trim()
  ) {
    return "Password is required.";
  }
  if (credentials.authType === "key" && !credentials.privateKey.trim()) {
    return "Private key is required.";
  }
  return null;
}

function formatKb(kb: number | null | undefined): string {
  if (kb == null) return "unknown";
  if (kb >= 1024 * 1024) return `${(kb / (1024 * 1024)).toFixed(1)} GB`;
  if (kb >= 1024) return `${(kb / 1024).toFixed(1)} MB`;
  return `${kb} KB`;
}

function DetailRow({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{label}</dt>
      <dd className="text-right font-medium">{children}</dd>
    </div>
  );
}

function NetworkInterfaces({
  interfaces,
}: {
  interfaces: NetworkInterfaceSummary[];
}) {
  if (interfaces.length === 0) {
    return <span className="text-muted-foreground">none detected</span>;
  }
  return (
    <ul className="space-y-1 text-right">
      {interfaces.map((iface) => (
        <li key={iface.name}>
          <span className={cn(iface.up ? "" : "text-muted-foreground")}>
            {iface.name}
          </span>
          {iface.proto ? ` · ${iface.proto}` : ""}
          {iface.addresses.length > 0
            ? ` · ${iface.addresses.map((a) => a.address).join(", ")}`
            : ""}
        </li>
      ))}
    </ul>
  );
}

function WirelessRadios({ radios }: { radios: WifiRadioSummary[] }) {
  if (radios.length === 0) {
    return <span className="text-muted-foreground">none detected</span>;
  }
  return (
    <ul className="space-y-1 text-right">
      {radios.map((radio) => (
        <li key={radio.name}>
          <span className={cn(radio.up ? "" : "text-muted-foreground")}>
            {radio.band ?? "Wireless"}
          </span>
          {radio.ssid ? ` · ${radio.ssid}` : ""}
          {radio.channel != null ? ` · ch ${radio.channel}` : ""}
          {radio.station_count > 0
            ? ` · ${radio.station_count} client${radio.station_count === 1 ? "" : "s"}`
            : ""}
        </li>
      ))}
    </ul>
  );
}

function SummaryCard({ info }: { info: DeviceInfo }) {
  const cpu = info.cpu ?? null;
  const memory = info.memory ?? null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <CheckCircle2 className="size-5 text-emerald-600" aria-hidden />
          Connected
        </CardTitle>
        <CardDescription>
          Verified over SSH. Review the device summary and save it to the
          dashboard.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <dl className="space-y-2 text-sm">
          <DetailRow label="Hostname">
            {info.hostname ?? "unknown"}
          </DetailRow>
          <DetailRow label="OpenWrt Version">
            {info.firmware ?? "unknown"}
          </DetailRow>
          <DetailRow label="Model">
            {info.model ?? "unknown"}
          </DetailRow>
          <DetailRow label="Kernel">
            {info.kernel ?? "unknown"}
          </DetailRow>
          <DetailRow label="Architecture">
            {info.architecture ?? "unknown"}
          </DetailRow>
          <DetailRow label="CPU">
            {cpu?.cores != null ? `${cpu.cores} core${cpu.cores === 1 ? "" : "s"}` : "unknown"}
            {cpu?.usage_percent != null ? ` · ${cpu.usage_percent.toFixed(1)}% load` : ""}
          </DetailRow>
          <DetailRow label="Memory">
            {memory?.used_percent != null ? `${memory.used_percent.toFixed(1)}% used` : "unknown"}
            {memory ? ` · ${formatKb(memory.used_kb)} / ${formatKb(memory.total_kb)}` : ""}
          </DetailRow>
          <DetailRow label="Network Interfaces">
            <NetworkInterfaces interfaces={info.network_interfaces ?? []} />
          </DetailRow>
          <DetailRow label="Wireless Radios">
            <WirelessRadios radios={info.wifi_radios ?? []} />
          </DetailRow>
          <DetailRow label="Installed Packages">
            {info.packages_count ?? 0}
          </DetailRow>
        </dl>
      </CardContent>
    </Card>
  );
}

function WelcomeView({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex flex-col items-center gap-6 text-center">
      <span className="flex size-16 items-center justify-center rounded-2xl border bg-muted">
        <Logo className="size-8" />
      </span>
      <div className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">
          OpenWrt AI Copilot
        </h1>
        <p className="mx-auto max-w-md text-muted-foreground">
          Connect your OpenWrt router over SSH to unlock live telemetry and an
          AI copilot for your network. Everything runs locally — no accounts,
          no cloud, no fake data.
        </p>
      </div>
      <Button size="lg" onClick={onStart}>
        Add First Router
      </Button>
    </div>
  );
}

function RouterInfoForm({
  credentials,
  name,
  setName,
  onChange,
  error,
  testing,
  onBack,
  onTest,
}: {
  credentials: RouterCredentials;
  name: string;
  setName: (value: string) => void;
  onChange: (patch: Partial<RouterCredentials>) => void;
  error: string | null;
  testing: boolean;
  onBack: () => void;
  onTest: () => void;
}) {
  const authIsKey = credentials.authType === "key";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Router information</CardTitle>
        <CardDescription>
          How the copilot should reach your OpenWrt device over SSH.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="space-y-1.5">
          <Label htmlFor="name">Router Name</Label>
          <Input
            id="name"
            placeholder="Living room router"
            value={name}
            onChange={(event) => setName(event.target.value)}
            maxLength={128}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-[1fr_110px_1fr]">
          <div className="space-y-1.5">
            <Label htmlFor="host">Host / IP Address</Label>
            <Input
              id="host"
              placeholder="192.168.1.1"
              value={credentials.host}
              onChange={(event) => onChange({ host: event.target.value })}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="port">SSH Port</Label>
            <Input
              id="port"
              type="number"
              min={1}
              max={65535}
              value={credentials.port}
              onChange={(event) =>
                onChange({ port: Number(event.target.value) || 22 })
              }
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="username">Username</Label>
            <Input
              id="username"
              placeholder="root"
              value={credentials.username}
              onChange={(event) => onChange({ username: event.target.value })}
            />
          </div>
        </div>

        <fieldset className="space-y-1.5">
          <legend className="text-sm font-medium leading-none">
            Authentication Method
          </legend>
          <div className="flex flex-col gap-2 sm:flex-row">
            <label
              className={cn(
                "flex flex-1 cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                !authIsKey
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              <input
                type="radio"
                name="auth-method"
                className="size-3.5"
                checked={!authIsKey}
                onChange={() => onChange({ authType: "password" })}
              />
              Password
            </label>
            <label
              className={cn(
                "flex flex-1 cursor-pointer items-center gap-2 rounded-md border px-3 py-2 text-sm font-medium transition-colors",
                authIsKey
                  ? "border-primary bg-primary/10 text-primary"
                  : "border-border text-muted-foreground hover:text-foreground",
              )}
            >
              <input
                type="radio"
                name="auth-method"
                className="size-3.5"
                checked={authIsKey}
                onChange={() => onChange({ authType: "key" })}
              />
              SSH Private Key
            </label>
          </div>
        </fieldset>

        {authIsKey ? (
          <div className="space-y-1.5">
            <Label htmlFor="private-key">Private Key</Label>
            <textarea
              id="private-key"
              rows={6}
              placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
              value={credentials.privateKey}
              onChange={(event) => onChange({ privateKey: event.target.value })}
              className="w-full rounded-md border border-input bg-transparent px-3 py-2 font-mono text-sm shadow-xs outline-none transition-[color,box-shadow] placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-ring/50 focus-visible:ring-[3px]"
            />
            <p className="text-xs text-muted-foreground">
              Paste the full key, including the BEGIN/END lines.
            </p>
          </div>
        ) : (
          <div className="space-y-1.5">
            <Label htmlFor="password">Password</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              value={credentials.password}
              onChange={(event) => onChange({ password: event.target.value })}
            />
          </div>
        )}

        {error ? (
          <p className="rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {error}
          </p>
        ) : null}
      </CardContent>
      <CardFooter className="flex flex-wrap justify-between gap-2">
        <Button variant="outline" onClick={onBack}>
          Back
        </Button>
        <Button onClick={onTest} disabled={testing}>
          {testing ? (
            <Loader2 className="size-4 animate-spin" aria-hidden />
          ) : null}
          Test Connection
        </Button>
      </CardFooter>
    </Card>
  );
}

export default function OnboardingPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(true);
  const [view, setView] = useState<View>("welcome");
  const [credentials, setCredentials] = useState<RouterCredentials>(
    DEFAULT_CREDENTIALS,
  );
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);
  const [deviceInfo, setDeviceInfo] = useState<DeviceInfo | null>(null);
  const [saving, setSaving] = useState(false);
  const currentRouterRef = useRef<SavedRouter | null>(null);

  useEffect(() => {
    let cancelled = false;
    listConnections()
      .then((data) => {
        if (cancelled) {
          return;
        }
        // Re-onboarding an existing router: the wizard was re-opened with
        // ?reconnect=<id> (or ?reconnect for the most recent router), so it is
        // allowed to run even though a router is already configured, and it
        // targets that specific record (edit, never add).
        const params = new URLSearchParams(window.location.search);
        const reconnect = params.get("reconnect");
        const add = params.get("add");
        const saved = data.routers;
        if (reconnect !== null && saved.length > 0) {
          const target =
            saved.find((item) => String(item.id) === reconnect) ?? saved[0];
          currentRouterRef.current = target;
          setCredentials((prev) => ({
            ...prev,
            host: target.host,
            port: target.port,
            username: target.username,
          }));
          setName(target.name);
          setLoading(false);
          return;
        }
        // Explicit "add a new router" from Settings: show the blank wizard
        // even when a router is already configured (distinct from reconnect).
        if (add !== null) {
          currentRouterRef.current = null;
          setLoading(false);
          return;
        }
        if (saved.length > 0) {
          router.replace("/dashboard");
          return;
        }
        setLoading(false);
      })
      .catch(() => {
        if (!cancelled) {
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  function handleChange(patch: Partial<RouterCredentials>) {
    setCredentials((prev) => ({ ...prev, ...patch }));
    setError(null);
  }

  async function handleTestConnection() {
    const validation = validateCredentials(credentials);
    if (validation) {
      setError(validation);
      return;
    }
    setError(null);
    setTesting(true);
    setDeviceInfo(null);
    try {
      const info = await detectDevice(credentials);
      if (!info.ok) {
        setError(info.error ?? "Connection failed.");
        return;
      }
      setDeviceInfo(info);
      if (!name.trim()) {
        setName((info.hostname ?? info.model ?? "").trim());
      }
      setView("connected");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Connection test failed.",
      );
    } finally {
      setTesting(false);
    }
  }

  async function handleSave() {
    if (!name.trim()) {
      setError("Give the router a name.");
      setView("form");
      return;
    }
    setSaving(true);
    try {
      await saveRouter(name.trim(), credentials, currentRouterRef.current?.id);
      router.replace("/dashboard");
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Saving the router failed.",
      );
      setView("form");
    } finally {
      setSaving(false);
    }
  }

  if (loading) {
    return (
      <main className="flex min-h-screen flex-col">
        <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center gap-6 p-6">
          <Skeleton className="size-16 rounded-2xl" />
          <Skeleton className="h-8 w-64" />
          <Skeleton className="h-4 w-full max-w-md" />
          <Skeleton className="h-10 w-40" />
        </div>
        <Footer />
      </main>
    );
  }

  return (
    <main className="flex min-h-screen flex-col">
      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col justify-center gap-6 p-6">
      {view === "welcome" ? (
        <WelcomeView onStart={() => setView("form")} />
      ) : null}

      {view === "form" ? (
        <div className="space-y-6">
          <header className="space-y-1 text-center">
            <h1 className="flex items-center justify-center gap-2 text-2xl font-bold tracking-tight">
              <Logo className="size-6" />
              Connect your router
            </h1>
            <p className="text-sm text-muted-foreground">
              The copilot connects over SSH and never falls back to fake data.
            </p>
          </header>
          <RouterInfoForm
            credentials={credentials}
            name={name}
            setName={setName}
            onChange={handleChange}
            error={error}
            testing={testing}
            onBack={() => {
              setError(null);
              setView("welcome");
            }}
            onTest={handleTestConnection}
          />
        </div>
      ) : null}

      {view === "connected" && deviceInfo ? (
        <div className="space-y-6">
          <header className="space-y-1 text-center">
            <h1 className="flex items-center justify-center gap-2 text-2xl font-bold tracking-tight">
              <CheckCircle2 className="size-6 text-emerald-600" aria-hidden />
              Connected
            </h1>
            <p className="text-sm text-muted-foreground">
              <span className="font-medium text-foreground">{name}</span> ·{" "}
              {deviceInfo.host}:{credentials.port}
            </p>
          </header>
          <SummaryCard info={deviceInfo} />
          {error ? (
            <p className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/10 px-3 py-2 text-sm text-destructive">
              <XCircle className="size-4" aria-hidden />
              {error}
            </p>
          ) : null}
          <div className="flex flex-wrap justify-between gap-2">
            <Button
              variant="outline"
              onClick={() => {
                setError(null);
                setView("form");
              }}
            >
              Back
            </Button>
            <Button onClick={handleSave} disabled={saving}>
              {saving ? (
                <Loader2 className="size-4 animate-spin" aria-hidden />
              ) : (
                <Wifi className="size-4" aria-hidden />
              )}
              Save Router
            </Button>
          </div>
        </div>
      ) : null}

      <p className="text-center text-sm text-muted-foreground">
        Credentials are stored on this device and never shown again.
      </p>
      </div>
      <Footer />
    </main>
  );
}
