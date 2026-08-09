"""CPU collector.

Sources: ``ubus call system info`` for load averages and uptime;
``/proc/cpuinfo`` for core count and CPU/system model; a short-lived 2-sample
delta of ``/proc/stat`` for live CPU utilization (falls back to a load-derived
figure when ``/proc/stat`` cannot be sampled); cpufreq sysfs for current
frequency; Linux thermal zones for on-die temperature when present.

The collector is deliberately defensive about missing or malformed output so a
parser failure can never collapse CPU data to zeroes or NaN.
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import CpuInfo

#: OpenWrt ``ubus system info`` reports load averages as fixed-point integers in
#: units of 1/65536 so they round-trip with full precision. Floats (older or
#: alternative firmware) are used as-is.
_UBUS_LOAD_SCALE = 65536.0

#: Values >= this threshold and whole are treated as fixed-point loads. Real
#: load averages are always small, so this cleanly separates the two formats.
_FIXED_POINT_THRESHOLD = 1000.0

#: Keys that identify the CPU model across x86 / ARM / MIPS cpuinfo layouts.
_MODEL_KEYS = ("model name", "model", "Hardware", "cpu model")
#: Keys that identify the SoC / system type when no CPU model key is present.
_SOC_KEYS = ("system type", "Hardware", "machine")


def _to_float(value: object) -> float | None:
    """Return a finite float, or ``None`` when the value is unusable."""
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if number != number or number in (float("inf"), float("-inf")):
        return None
    return number


def _normalize_ubus_load(value: object) -> float | None:
    """Convert one ``ubus system info`` load entry into a floating load."""
    number = _to_float(value)
    if number is None:
        return None
    if number < 0:
        number = 0.0
    if number >= _FIXED_POINT_THRESHOLD and number % 1 == 0:
        number /= _UBUS_LOAD_SCALE
    return number


def _parse_cpuinfo(text: str) -> tuple[int, str | None]:
    """Return ``(cores, model)`` from ``/proc/cpuinfo``.

    Handles the common ``model name`` key (x86), ``Hardware`` (ARM single-board
    computers) and MIPS, where the field is often spelled ``cpu model`` or the
    SoC is exposed via ``system type``.
    """
    processors = 0
    model: str | None = None
    model_candidates: list[str] = []
    soc_candidates: list[str] = []
    for line in text.splitlines():
        key, _, value = line.partition(":")
        key = key.strip()
        value = value.strip()
        if not value:
            continue
        if key == "processor":
            processors += 1
        elif key in _MODEL_KEYS:
            model_candidates.append(value)
        elif key in _SOC_KEYS:
            soc_candidates.append(value)
    if model_candidates:
        model = model_candidates[0]
    elif soc_candidates:
        model = soc_candidates[0]
    return processors, model


def _thermal_celsius(ctx: CollectorContext) -> float | None:
    """Best-effort CPU temperature from the first usable thermal zone."""
    zones_raw = ctx.sh("ls /sys/class/thermal/", default="").split()
    zones = [z for z in zones_raw if z.startswith("thermal_zone")]
    for zone in zones:
        raw = ctx.sh(f"cat /sys/class/thermal/{zone}/temp", default="").strip()
        temperature = _to_float(raw)
        if temperature is not None:
            return round(temperature / 1000.0, 2)
    return None


def _proc_stat_sample(line: str) -> tuple[float, float] | None:
    """Return ``(total, idle)`` jiffies from an aggregate ``boot cpu ...`` line."""
    parts = line.split()
    if len(parts) < 5 or parts[0] != "cpu":
        return None
    values = [_to_float(raw) for raw in parts[1:]]
    if len(values) < 4 or any(v is None for v in values):
        return None
    total = sum(values)  # type: ignore[arg-type]
    idle = values[3] + (values[4] if len(values) > 4 else 0.0)  # type: ignore[index,operator]
    return total, idle


def _usage_from_stat(text: str) -> float | None:
    """Derive live utilization percent from two aggregate ``/proc/stat`` samples."""
    lines = [line for line in text.splitlines() if line.strip().startswith("cpu ")]
    if len(lines) < 2:
        return None
    first = _proc_stat_sample(lines[0])
    second = _proc_stat_sample(lines[1])
    if first is None or second is None:
        return None
    total_a, idle_a = first
    total_b, idle_b = second
    total_delta = total_b - total_a
    idle_delta = idle_b - idle_a
    if total_delta <= 0:
        return None
    busy = max(0.0, 1.0 - idle_delta / total_delta)
    return min(100.0, busy * 100.0)


class CpuCollector(Collector):
    name = "cpu"

    def collect(self, ctx: CollectorContext) -> CpuInfo:
        info: dict = {}
        with suppress(Exception):  # noqa: BLE001 - fall back to loadavg file
            info = ctx.ubus.call("system", "info")

        cores = 1
        model: str | None = None
        cpuinfo = ctx.sh("cat /proc/cpuinfo", default="")
        if cpuinfo:
            count, parsed_model = _parse_cpuinfo(cpuinfo)
            if count:
                cores = count
            model = parsed_model

        architecture: str | None = None
        if ctx.state.get("kernel"):
            architecture = getattr(ctx.state["kernel"], "architecture", None) or None

        freq = None
        freq_raw = ctx.sh(
            "cat /sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq", default=""
        ).strip()
        freq_float = _to_float(freq_raw)
        if freq_float is not None and freq_float > 0:
            freq = round(freq_float / 1000)

        load_1, load_5, load_15, uptime = self._load_metrics(ctx, info)

        usage: float | None = None
        stat_text = ctx.sh(
            "head -n1 /proc/stat; sleep 1 2>/dev/null || sleep 0; head -n1 /proc/stat",
            default="",
        )
        usage = _usage_from_stat(stat_text)

        return CpuInfo(
            load_1=round(load_1, 2) if load_1 is not None else 0.0,
            load_5=round(load_5, 2) if load_5 is not None else 0.0,
            load_15=round(load_15, 2) if load_15 is not None else 0.0,
            cores=cores,
            uptime_seconds=round(uptime, 1) if uptime is not None else 0.0,
            usage_percent=round(usage, 1) if usage is not None else None,
            frequency_mhz=freq,
            model=model,
            architecture=architecture,
            temperature_c=_thermal_celsius(ctx),
        )

    @staticmethod
    def _load_metrics(
        ctx: CollectorContext, info: dict
    ) -> tuple[float | None, float | None, float | None, float | None]:
        """Return (load_1, load_5, load_15, uptime) from the best sources.

        ``ubus system info`` supplies uptime, but its ``load`` payload varies by
        firmware: modern OpenWrt returns a fixed-point array, while other builds
        expose ``load_1/5/15`` keys. Any missing values are filled from
        ``/proc/loadavg`` / ``/proc/uptime`` and never crash the collector.
        """
        loads: list[float | None] = [None, None, None]
        uptime: float | None = _to_float(info.get("uptime"))

        system_load = info.get("load")
        if isinstance(system_load, (list, tuple)) and len(system_load) >= 1:
            for index in range(min(3, len(system_load))):
                loads[index] = _normalize_ubus_load(system_load[index])
        else:
            for index, key in enumerate(("load_1", "load_5", "load_15")):
                loads[index] = _normalize_ubus_load(info.get(key))

        loadavg_text = ctx.sh("cat /proc/loadavg", default="").split()
        for index, value in enumerate(loads):
            if value is None and index < len(loadavg_text):
                loads[index] = _to_float(loadavg_text[index])
            if loads[index] is None:
                loads[index] = 0.0

        if uptime is None:
            uptime_text = ctx.sh("cat /proc/uptime", default="").split()
            if uptime_text:
                uptime = _to_float(uptime_text[0])

        return loads[0], loads[1], loads[2], uptime