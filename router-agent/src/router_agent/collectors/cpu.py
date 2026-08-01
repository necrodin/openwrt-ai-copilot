"""CPU collector.

Sources: ``ubus call system info`` for load averages and uptime;
``/proc/cpuinfo`` for core count; cpufreq sysfs for current frequency.
"""

from __future__ import annotations

from contextlib import suppress

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import CpuInfo


class CpuCollector(Collector):
    name = "cpu"

    def collect(self, ctx: CollectorContext) -> CpuInfo:
        info = {}
        with suppress(Exception):  # noqa: BLE001 - fall back to loadavg file
            info = ctx.ubus.call("system", "info")

        cores = 1
        cpuinfo = ctx.sh("cat /proc/cpuinfo", default="")
        if cpuinfo:
            count = sum(1 for line in cpuinfo.splitlines() if line.startswith("processor"))
            if count:
                cores = count

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
        )
