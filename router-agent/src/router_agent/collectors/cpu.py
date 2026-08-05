"""CPU collector.

Sources: ``ubus call system info`` for load averages and uptime;
``/proc/cpuinfo`` for core count, model name, and architecture; cpufreq sysfs
for current frequency; Linux thermal zones for on-die temperature when present.
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import CpuInfo


def _parse_cpuinfo(text: str) -> tuple[int, str | None, str | None]:
    """Return ``(cores, model, architecture)`` from ``/proc/cpuinfo``."""
    processors = 0
    model: str | None = None
    architecture: str | None = None
    seen_models: set[str] = set()
    seen_arch: set[str] = set()
    for line in text.splitlines():
        key, _, value = line.partition(":")
        value = value.strip()
        key = key.strip()
        if key == "processor":
            processors += 1
        elif key == "model name" and value or key == "Hardware" and value:
            seen_models.add(value)
        elif key == "arch" and value or key == "model" and value:
            seen_arch.add(value)
    if seen_models:
        model = next(iter(seen_models))
    if seen_arch:
        architecture = next(iter(seen_arch))
    return processors, model, architecture


def _thermal_celsius(ctx: CollectorContext) -> float | None:
    """Best-effort CPU temperature from the first thermal zone."""
    zones_raw = ctx.sh("ls /sys/class/thermal/", default="").split()
    zones = [z for z in zones_raw if z.startswith("thermal_zone")]
    for zone in zones:
        raw = ctx.sh(f"cat /sys/class/thermal/{zone}/temp", default="").strip()
        if raw.lstrip("-").isdigit():
            return round(int(raw) / 1000, 2)
    return None


class CpuCollector(Collector):
    name = "cpu"

    def collect(self, ctx: CollectorContext) -> CpuInfo:
        info = {}
        with suppress(Exception):  # noqa: BLE001 - fall back to loadavg file
            info = ctx.ubus.call("system", "info")

        cores = 1
        model: str | None = None
        architecture: str | None = None
        cpuinfo = ctx.sh("cat /proc/cpuinfo", default="")
        if cpuinfo:
            count, parsed_model, parsed_arch = _parse_cpuinfo(cpuinfo)
            if count:
                cores = count
            model = parsed_model
            architecture = parsed_arch

        if architecture is None and ctx.state.get("kernel"):
            architecture = getattr(ctx.state["kernel"], "architecture", None) or None

        freq = None
        freq_raw = ctx.sh(
            "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", default=""
        ).strip()
        if freq_raw.isdigit():
            freq = round(int(freq_raw) / 1000)

        load_1 = float(info.get("load_1", 0.0) or 0.0)
        load_5 = float(info.get("load_5", 0.0) or 0.0)
        load_15 = float(info.get("load_15", 0.0) or 0.0)
        uptime = float(info.get("uptime", 0.0) or 0.0)

        if not info:
            loadavg = ctx.sh("cat /proc/loadavg", default="").split()
            if len(loadavg) >= 3:
                load_1 = float(loadavg[0])
                load_5 = float(loadavg[1])
                load_15 = float(loadavg[2])

        return CpuInfo(
            load_1=round(load_1, 2),
            load_5=round(load_5, 2),
            load_15=round(load_15, 2),
            cores=cores,
            uptime_seconds=round(uptime, 1),
            usage_percent=round(min(100.0, (load_1 / cores) * 100.0), 1) if cores else None,
            frequency_mhz=freq,
            model=model,
            architecture=architecture,
            temperature_c=_thermal_celsius(ctx),
        )
