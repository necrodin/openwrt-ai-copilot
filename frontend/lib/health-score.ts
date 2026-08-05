import type { DeviceSnapshot } from "@/lib/dashboard";
import { isWan } from "@/lib/dashboard-utils";

export type HealthTone = "excellent" | "good" | "fair" | "poor";

export type HealthFactorStatus = "ok" | "warn" | "bad";

export type HealthFactor = {
  label: string;
  detail: string;
  status: HealthFactorStatus;
};

export type HealthScoreResult = {
  score: number;
  tone: HealthTone;
  factors: HealthFactor[];
};

function clamp(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

/**
 * Computes a 0–100 health score from a live device snapshot, plus the list of
 * contributing factors shown inside the Health Score widget. Pure UI logic —
 * no backend involvement.
 */
export function computeHealthScore(
  snapshot: DeviceSnapshot | null,
): HealthScoreResult | null {
  if (snapshot === null) {
    return null;
  }

  let score = 100;
  const deduct = (amount: number) => {
    score -= amount;
  };
  const factors: HealthFactor[] = [];

  const cpu = snapshot.cpu;
  const usage = cpu?.usage_percent ?? null;
  if (usage === null) {
    factors.push({ label: "CPU", detail: "No telemetry", status: "warn" });
  } else if (usage >= 85) {
    deduct(20);
    factors.push({ label: "CPU", detail: `${usage.toFixed(0)}% load`, status: "bad" });
  } else if (usage >= 65) {
    deduct(10);
    factors.push({ label: "CPU", detail: `${usage.toFixed(0)}% load`, status: "warn" });
  } else {
    factors.push({ label: "CPU", detail: `${usage.toFixed(0)}% load`, status: "ok" });
  }

  const memory = snapshot.memory;
  const memPercent =
    memory !== null && memory.total_kb > 0
      ? (memory.used_kb / memory.total_kb) * 100
      : null;
  if (memPercent === null) {
    factors.push({ label: "Memory", detail: "No telemetry", status: "warn" });
  } else if (memPercent >= 90) {
    deduct(20);
    factors.push({ label: "Memory", detail: `${memPercent.toFixed(0)}% used`, status: "bad" });
  } else if (memPercent >= 75) {
    deduct(10);
    factors.push({ label: "Memory", detail: `${memPercent.toFixed(0)}% used`, status: "warn" });
  } else {
    factors.push({ label: "Memory", detail: `${memPercent.toFixed(0)}% used`, status: "ok" });
  }

  if (snapshot.storage.length > 0) {
    const storageMax = Math.max(
      0,
      ...snapshot.storage.map((mount) => mount.use_percent ?? 0),
    );
    if (storageMax >= 90) {
      deduct(15);
      factors.push({ label: "Storage", detail: `${storageMax.toFixed(0)}% used`, status: "bad" });
    } else if (storageMax >= 75) {
      deduct(8);
      factors.push({ label: "Storage", detail: `${storageMax.toFixed(0)}% used`, status: "warn" });
    } else {
      factors.push({ label: "Storage", detail: `${storageMax.toFixed(0)}% used`, status: "ok" });
    }
  }

  const hasDefaultRoute = snapshot.routing.some(
    (route) =>
      route.family === "ipv4" &&
      (route.destination === "0.0.0.0/0" || route.destination === "default"),
  );
  const wan = snapshot.network.find(isWan);
  const wanUp = wan?.up === true;
  if (!hasDefaultRoute || !wanUp) {
    deduct(25);
    factors.push({ label: "WAN", detail: "No active uplink", status: "bad" });
  } else {
    const ip = wan?.addresses.find((address) => address.family === "ipv4")?.address;
    factors.push({
      label: "WAN",
      detail: ip ? `Online ${ip}` : "Online",
      status: "ok",
    });
  }

  const temperature = snapshot.temperature;
  const hottest = temperature.reduce(
    (max, reading) => Math.max(max, reading.temperature_c),
    0,
  );
  if (temperature.length > 0) {
    if (hottest >= 75) {
      deduct(15);
      factors.push({ label: "Temperature", detail: `${hottest.toFixed(0)}°C`, status: "bad" });
    } else if (hottest >= 60) {
      deduct(8);
      factors.push({ label: "Temperature", detail: `${hottest.toFixed(0)}°C`, status: "warn" });
    } else {
      factors.push({ label: "Temperature", detail: `${hottest.toFixed(0)}°C`, status: "ok" });
    }
  }

  const tunnels = snapshot.vpn;
  if (tunnels.length > 0) {
    const down = tunnels.filter((tunnel) => !tunnel.up).length;
    if (down > 0) {
      deduct(5);
      factors.push({ label: "VPN", detail: `${down} tunnel(s) down`, status: "warn" });
    } else {
      factors.push({ label: "VPN", detail: `${tunnels.length} tunnel(s) up`, status: "ok" });
    }
  }

  const radios = snapshot.wifi.radios;
  if (radios.length > 0) {
    const up = radios.filter((radio) => radio.up).length;
    if (up === 0) {
      deduct(10);
      factors.push({ label: "Wireless", detail: "All radios down", status: "bad" });
    } else {
      factors.push({ label: "Wireless", detail: `${up} radio(s) up`, status: "ok" });
    }
  }

  const tone: HealthTone =
    score >= 80 ? "excellent" : score >= 60 ? "good" : score >= 40 ? "fair" : "poor";

  return { score: clamp(score), tone, factors };
}
