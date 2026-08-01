"""Installed packages collector.

Source: ``opkg list-installed``. Each line is ``name - version - description``.
"""

from __future__ import annotations

from router_agent.collectors.base import Collector, CollectorContext
from router_agent.model import Package


def _parse_opkg(text: str) -> list[Package]:
    packages: list[Package] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        name, sep, rest = line.partition(" - ")
        if not sep:
            continue
        version, _, description = rest.partition(" - ")
        packages.append(
            Package(name=name.strip(), version=version.strip(), description=description.strip())
        )
    return packages


class PackagesCollector(Collector):
    name = "packages"

    def collect(self, ctx: CollectorContext) -> list[Package]:
        return _parse_opkg(ctx.sh("opkg list-installed", default=""))
