"""Installed packages collector.

OpenWrt 25+ ships the ``apk`` package manager (``apk list --installed``), while
older releases use ``opkg`` (``opkg list-installed``). The active manager is
detected by checking the ``apk`` binary; opkg is the fallback so 22.x–24.x
devices keep reporting packages unchanged.
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


def _split_apk_pkgid(pkgid: str) -> tuple[str, str]:
    """Split an apk package id ``name-version`` into its two parts.

    apk package ids are ``<name>-<version>`` where the version frequently
    contains dashes itself (e.g. ``base-files-258-r0``). The version fragment
    always starts with a digit (it may carry an epoch like ``1:25.0.0``), so we
    scan for the first dash-separated fragment that begins with a digit.
    """
    parts = pkgid.split("-")
    for index in range(1, len(parts)):
        if parts[index][:1].isdigit():
            return "-".join(parts[:index]), "-".join(parts[index:])
    return pkgid, ""


def _parse_apk(text: str) -> list[Package]:
    packages: list[Package] = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # Never treat apk diagnostics (e.g. ``WARNING: opening from cache ...``
        # when stderr is captured into the same stream) as a package.
        if line.startswith(("WARNING:", "ERROR:")):
            continue
        pkgid = line.split()[0]
        # A real apk package id always carries a digit (its version — possibly
        # with an epoch like ``luci-1:25.0.0``); diagnostic or shell-error
        # tokens never do, so they are not packages.
        if not any(char.isdigit() for char in pkgid):
            continue
        name, version = _split_apk_pkgid(pkgid)
        if not name:
            continue
        packages.append(Package(name=name, version=version))
    return packages


class PackagesCollector(Collector):
    name = "packages"

    def collect(self, ctx: CollectorContext) -> list[Package]:
        has_apk = bool(ctx.sh("command -v apk", default="").strip())
        if has_apk:
            return _parse_apk(ctx.sh("apk list --installed", default=""))
        return _parse_opkg(ctx.sh("opkg list-installed", default=""))
