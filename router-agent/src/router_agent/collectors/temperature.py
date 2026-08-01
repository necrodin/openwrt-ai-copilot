"""Temperature collector.

Reads Linux thermal zones under ``/sys/class/thermal``. Not every device has
sensors; an empty list is a valid (informative) result.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import TemperatureReading


class TemperatureCollector(Collector):
    name = "temperature"

    def collect(self, ctx: CollectorContext) -> list[TemperatureReading]:
        zones_raw = ctx.sh("ls /sys/class/thermal/", default="").split()
        zones = [z for z in zones_raw if z.startswith("thermal_zone")]
        readings: list[TemperatureReading] = []
        for zone in zones:
            temp = ctx.sh(f"cat /sys/class/thermal/{zone}/temp", default="").strip()
            if not temp.isdigit():
                continue
            zone_type = ctx.sh(f"cat /sys/class/thermal/{zone}/type", default=zone).strip()
            readings.append(
                TemperatureReading(
                    zone=zone_type or zone,
                    temperature_c=round(int(temp) / 1000, 2),
                )
            )
        return readings
